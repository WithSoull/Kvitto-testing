import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Tariff
from app.domain.enums import PaymentMethod
from app.domain.errors import IdempotencyKeyReusedError, PaymentNotFoundError, UnknownTariffError
from app.domain.money import build_schedule, calc_discount
from app.domain.promo import promo_discount_percent
from app.schemas.payment import PaymentCreate


def request_fingerprint(data: PaymentCreate) -> str:
    """SHA-256 of the normalized request, to detect a reused key with a different body."""
    canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def create_payment(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str | None
) -> tuple[Payment, bool]:
    """Create a payment or replay the one created earlier with the same key.

    Returns the payment and whether it was created by this call.
    """
    request_hash = request_fingerprint(data) if idempotency_key is not None else None

    # Fast path for a repeated request. Correctness under concurrency is
    # guaranteed by ON CONFLICT below, not by this check.
    if idempotency_key is not None:
        existing = await _find_by_idempotency_key(session, idempotency_key)
        if existing is not None:
            return _replay(existing, idempotency_key, request_hash), False

    tariff = await session.get(Tariff, data.tariff_id)
    if tariff is None:
        raise UnknownTariffError(data.tariff_id)

    discount = calc_discount(tariff.price, promo_discount_percent(data.promo_code))
    amount = tariff.price - discount
    schedule = None
    if data.method is PaymentMethod.INSTALLMENT:
        assert data.installment_months is not None  # guaranteed by PaymentCreate
        schedule = build_schedule(amount, data.installment_months)

    statement = (
        insert(Payment)
        .values(
            tariff_id=tariff.id,
            email=data.email,
            method=data.method,
            installment_months=data.installment_months,
            price=tariff.price,
            discount=discount,
            amount=amount,
            promo_code=data.promo_code,
            schedule=schedule,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        .on_conflict_do_nothing(index_elements=[Payment.idempotency_key])
        .returning(Payment)
    )
    payment = (await session.scalars(statement)).one_or_none()

    if payment is None:
        # A concurrent request with the same key committed first: replay its payment.
        assert idempotency_key is not None  # NULL keys never conflict
        existing = await _find_by_idempotency_key(session, idempotency_key)
        assert existing is not None
        return _replay(existing, idempotency_key, request_hash), False

    await session.commit()
    return payment, True


async def get_payment(session: AsyncSession, payment_id: UUID) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise PaymentNotFoundError(payment_id)
    return payment


async def _find_by_idempotency_key(session: AsyncSession, key: str) -> Payment | None:
    result = await session.scalars(select(Payment).where(Payment.idempotency_key == key))
    return result.one_or_none()


def _replay(existing: Payment, key: str, request_hash: str | None) -> Payment:
    if existing.request_hash != request_hash:
        raise IdempotencyKeyReusedError(key)
    return existing
