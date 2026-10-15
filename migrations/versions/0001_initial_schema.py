"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-15 14:20:38.386741
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tariffs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("price > 0", name=op.f("ck_tariffs_price_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tariffs")),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        # Enums are plain VARCHAR columns; allowed values are enforced by the CHECKs below.
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("tariff_id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("installment_months", sa.SmallInteger(), nullable=True),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("discount", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("promo_code", sa.String(length=32), nullable=True),
        sa.Column("schedule", postgresql.ARRAY(sa.BigInteger()), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name=op.f("ck_payments_status"),
        ),
        sa.CheckConstraint(
            "method IN ('card', 'sbp', 'installment')",
            name=op.f("ck_payments_method"),
        ),
        sa.CheckConstraint("discount >= 0", name=op.f("ck_payments_discount_non_negative")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.CheckConstraint(
            "amount = price - discount", name=op.f("ck_payments_amount_matches_price")
        ),
        sa.CheckConstraint(
            "installment_months IN (3, 6, 12)",
            name=op.f("ck_payments_installment_months_allowed"),
        ),
        sa.CheckConstraint(
            "(method = 'installment') = (installment_months IS NOT NULL)",
            name=op.f("ck_payments_installment_months_iff_installment"),
        ),
        sa.CheckConstraint(
            "(method = 'installment') = (schedule IS NOT NULL)",
            name=op.f("ck_payments_schedule_iff_installment"),
        ),
        sa.CheckConstraint(
            "(idempotency_key IS NULL) = (request_hash IS NULL)",
            name=op.f("ck_payments_idempotency_key_with_hash"),
        ),
        sa.ForeignKeyConstraint(
            ["tariff_id"], ["tariffs.id"], name=op.f("fk_payments_tariff_id_tariffs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payments_idempotency_key")),
    )
    op.create_index(op.f("ix_payments_created_at"), "payments", ["created_at"])
    op.create_index(op.f("ix_payments_email"), "payments", ["email"])
    op.create_index(op.f("ix_payments_status"), "payments", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_email"), table_name="payments")
    op.drop_index(op.f("ix_payments_created_at"), table_name="payments")
    op.drop_table("payments")
    op.drop_table("tariffs")
