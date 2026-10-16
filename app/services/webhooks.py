from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.domain.enums import PaymentStatus
from app.domain.errors import PaymentNotFoundError
from app.domain.status import ensure_transition_allowed


async def apply_bank_status(
    session: AsyncSession, payment_id: UUID, new_status: PaymentStatus
) -> None:
    # FOR UPDATE serializes webhooks for the same payment: a concurrent one waits for
    # this transaction and then checks the transition against the committed status.
    # populate_existing makes sure we use that fresh row, not a stale in-session copy.
    query = (
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    payment = await session.scalar(query)
    if payment is None:
        raise PaymentNotFoundError(payment_id)

    ensure_transition_allowed(payment.status, new_status)
    payment.status = new_status
    await session.commit()
