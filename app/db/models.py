from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import PaymentMethod, PaymentStatus


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR + CHECK instead of a native Postgres ENUM, storing member values."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        # By default SQLAlchemy stores member *names* ("PENDING"); we want values ("pending").
        values_callable=lambda members: [member.value for member in members],
    )


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (CheckConstraint("price > 0", name="price_positive"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(BigInteger)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("discount >= 0", name="discount_non_negative"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("amount = price - discount", name="amount_matches_price"),
        CheckConstraint("installment_months IN (3, 6, 12)", name="installment_months_allowed"),
        CheckConstraint(
            "(method = 'installment') = (installment_months IS NOT NULL)",
            name="installment_months_iff_installment",
        ),
        CheckConstraint(
            "(method = 'installment') = (schedule IS NOT NULL)",
            name="schedule_iff_installment",
        ),
        CheckConstraint(
            "(idempotency_key IS NULL) = (request_hash IS NULL)",
            name="idempotency_key_with_hash",
        ),
    )
    # Fetch server-generated columns (created_at, updated_at) via RETURNING on INSERT/UPDATE.
    # Otherwise they are expired and reading them would trigger a lazy load, which async forbids.
    # RUF012 is silenced: SQLAlchemy declares __mapper_args__ as an instance attribute,
    # so mypy rejects the ClassVar annotation ruff asks for.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus, "status"),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
        index=True,
    )
    tariff_id: Mapped[str] = mapped_column(String(32), ForeignKey("tariffs.id"))
    email: Mapped[str] = mapped_column(String(320), index=True)
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod, "method"))
    installment_months: Mapped[int | None] = mapped_column(SmallInteger)
    # Tariff price at creation time, so later price changes do not affect existing payments.
    price: Mapped[int] = mapped_column(BigInteger)
    discount: Mapped[int] = mapped_column(BigInteger)
    amount: Mapped[int] = mapped_column(BigInteger)
    promo_code: Mapped[str | None] = mapped_column(String(32))
    schedule: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
