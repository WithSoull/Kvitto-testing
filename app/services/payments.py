import hashlib
import json
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Tariff
from app.domain.enums import PaymentStatus
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
    # PaymentCreate guarantees installment_months is set exactly for the installment method.
    months = data.installment_months
    schedule = build_schedule(amount, months) if months is not None else None

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
        # Only a non-NULL key can conflict: a concurrent request with it committed first.
        existing = (
            await _find_by_idempotency_key(session, idempotency_key)
            if idempotency_key is not None
            else None
        )
        if existing is None or idempotency_key is None:
            # Unreachable while the unique index exists; fail loudly instead of returning nothing.
            raise RuntimeError("INSERT was skipped, but no payment with this key exists")
        return _replay(existing, idempotency_key, request_hash), False

    await session.commit()
    return payment, True


async def get_payment(session: AsyncSession, payment_id: UUID) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise PaymentNotFoundError(payment_id)
    return payment


async def list_payments(
    session: AsyncSession,
    *,
    email: str | None,
    status: PaymentStatus | None,
    limit: int,
    offset: int,
) -> Sequence[Payment]:
    query = select(Payment)
    if email is not None:
        # Emails are stored lower-cased, so an equality match on the index is case-insensitive.
        query = query.where(Payment.email == email.strip().lower())
    if status is not None:
        query = query.where(Payment.status == status)
    # id breaks ties between equal timestamps, so pages never overlap or skip rows.
    query = query.order_by(Payment.created_at.desc(), Payment.id.desc()).limit(limit).offset(offset)
    result = await session.scalars(query)
    return result.all()


async def _find_by_idempotency_key(session: AsyncSession, key: str) -> Payment | None:
    result = await session.scalars(select(Payment).where(Payment.idempotency_key == key))
    return result.one_or_none()


def _replay(existing: Payment, key: str, request_hash: str | None) -> Payment:
    if existing.request_hash != request_hash:
        raise IdempotencyKeyReusedError(key)
    return existing
