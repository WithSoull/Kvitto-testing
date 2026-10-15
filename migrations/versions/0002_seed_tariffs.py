"""seed tariffs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A frozen copy of the table shape: migrations must not import app models,
# which keep changing after this migration is written.
tariffs = sa.table(
    "tariffs",
    sa.column("id", sa.String),
    sa.column("title", sa.String),
    sa.column("price", sa.BigInteger),
)

TARIFFS = [
    {"id": "basic", "title": "Basic", "price": 990000},
    {"id": "standard", "title": "Standard", "price": 1990000},
    {"id": "premium", "title": "Premium", "price": 2990000},
]


def upgrade() -> None:
    op.bulk_insert(tariffs, TARIFFS)


def downgrade() -> None:
    op.execute(tariffs.delete().where(tariffs.c.id.in_([t["id"] for t in TARIFFS])))
