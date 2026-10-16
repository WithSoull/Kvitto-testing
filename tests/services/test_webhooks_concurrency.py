"""Status transitions under real concurrency.

Committing sessions, same approach as test_payments_concurrency.py.
"""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import Payment
from app.domain.enums import PaymentMethod, PaymentStatus
from app.domain.errors import InvalidTransitionError
from app.services.webhooks import apply_bank_status

Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(engine: AsyncEngine) -> Sessions:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def payment_id(sessions: Sessions) -> AsyncIterator[UUID]:
    async with sessions() as session:
        payment = Payment(
            tariff_id="basic",
            email="race@example.com",
            method=PaymentMethod.CARD,
            price=990000,
            discount=0,
            amount=990000,
        )
        session.add(payment)
        await session.commit()
    yield payment.id
    async with sessions() as session:
        await session.execute(delete(Payment).where(Payment.id == payment.id))
        await session.commit()


async def test_concurrent_webhook_sees_committed_status(
    sessions: Sessions, payment_id: UUID
) -> None:
    """pending -> succeeded commits while pending -> failed waits on the row lock.

    The waiting webhook must re-check the transition against the committed status
    (succeeded -> failed is forbidden) instead of overwriting it.
    """
    async with sessions() as first:
        locked = await first.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        assert locked is not None
        locked.status = PaymentStatus.SUCCEEDED
        await first.flush()

        async def second_webhook() -> None:
            async with sessions() as second:
                await apply_bank_status(second, payment_id, PaymentStatus.FAILED)

        task = asyncio.create_task(second_webhook())
        await asyncio.sleep(0.3)
        assert not task.done(), "second webhook should wait on the row lock"

        await first.commit()
        with pytest.raises(InvalidTransitionError):
            await task

    async with sessions() as session:
        assert (
            await session.scalar(select(Payment.status).where(Payment.id == payment_id))
            == PaymentStatus.SUCCEEDED
        )
