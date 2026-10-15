from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, Tariff
from app.domain.enums import PaymentMethod, PaymentStatus


def valid_payment(**overrides: Any) -> Payment:
    fields: dict[str, Any] = {
        "tariff_id": "standard",
        "email": "user@example.com",
        "method": PaymentMethod.INSTALLMENT,
        "installment_months": 3,
        "price": 1990000,
        "discount": 199000,
        "amount": 1791000,
        "promo_code": "KVITTO10",
        "schedule": [597000, 597000, 597000],
    }
    return Payment(**(fields | overrides))


async def test_tariffs_are_seeded(db_session: AsyncSession) -> None:
    tariffs = (await db_session.scalars(select(Tariff).order_by(Tariff.price))).all()

    assert [(t.id, t.title, t.price) for t in tariffs] == [
        ("basic", "Basic", 990000),
        ("standard", "Standard", 1990000),
        ("premium", "Premium", 2990000),
    ]


async def test_payment_defaults_and_enum_storage(db_session: AsyncSession) -> None:
    payment = valid_payment()
    db_session.add(payment)
    await db_session.flush()

    assert payment.id is not None
    assert payment.status == PaymentStatus.PENDING
    assert payment.created_at is not None
    # Enums must be stored by value ("pending"), not by member name ("PENDING").
    row = (
        await db_session.execute(
            text("SELECT status, method FROM payments WHERE id = :id"), {"id": payment.id}
        )
    ).one()
    assert tuple(row) == ("pending", "installment")


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"amount": 1791001}, "ck_payments_amount_matches_price"),
        ({"price": 0, "discount": 0, "amount": 0}, "ck_payments_amount_positive"),
        ({"discount": -1, "amount": 1990001}, "ck_payments_discount_non_negative"),
        ({"installment_months": 4}, "ck_payments_installment_months_allowed"),
        (
            {"method": PaymentMethod.CARD, "schedule": None},
            "ck_payments_installment_months_iff_installment",
        ),
        ({"schedule": None}, "ck_payments_schedule_iff_installment"),
        ({"idempotency_key": "key-1"}, "ck_payments_idempotency_key_with_hash"),
        ({"tariff_id": "gold"}, "fk_payments_tariff_id_tariffs"),
    ],
)
async def test_payment_constraints(
    db_session: AsyncSession, overrides: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        async with db_session.begin_nested():
            db_session.add(valid_payment(**overrides))


async def test_idempotency_key_is_unique(db_session: AsyncSession) -> None:
    key = {"idempotency_key": "key-1", "request_hash": "a" * 64}
    db_session.add(valid_payment(**key))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_payments_idempotency_key"):
        async with db_session.begin_nested():
            db_session.add(valid_payment(**key))


def test_migrations_downgrade_and_upgrade_from_scratch(alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
