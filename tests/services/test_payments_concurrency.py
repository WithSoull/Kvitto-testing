"""Idempotency under real concurrency.

These tests commit for real: a race needs separate connections, which the
rolled-back `db_session` fixture cannot provide. Rows are cleaned up by key.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import Payment
from app.domain.enums import PaymentMethod
from app.schemas.payment import PaymentCreate
from app.services.payments import create_payment, request_fingerprint

KEY = "concurrency-test-key"
DATA = PaymentCreate(tariff_id="standard", email="user@example.com", method=PaymentMethod.CARD)

Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(engine: AsyncEngine) -> AsyncIterator[Sessions]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    async with factory() as session:
        await session.execute(delete(Payment).where(Payment.idempotency_key == KEY))
        await session.commit()


async def count_by_key(sessions: Sessions) -> int:
    async with sessions() as session:
        query = select(func.count()).select_from(Payment).where(Payment.idempotency_key == KEY)
        return await session.scalar(query) or 0


async def test_parallel_requests_with_same_key_create_one_payment(sessions: Sessions) -> None:
    async def attempt() -> tuple[str, bool]:
        async with sessions() as session:
            payment, created = await create_payment(session, DATA, KEY)
            return str(payment.id), created

    results = await asyncio.gather(*(attempt() for _ in range(5)))

    assert len({payment_id for payment_id, _ in results}) == 1
    assert sorted(created for _, created in results) == [False] * 4 + [True]
    assert await count_by_key(sessions) == 1


async def test_insert_conflict_replays_concurrently_committed_payment(sessions: Sessions) -> None:
    """Forces the ON CONFLICT path: the fast-path lookup cannot see an uncommitted row."""
    async with sessions() as blocker:
        competitor = Payment(
            tariff_id="standard",
            email="user@example.com",
            method=PaymentMethod.CARD,
            price=1990000,
            discount=0,
            amount=1990000,
            idempotency_key=KEY,
            request_hash=request_fingerprint(DATA),
        )
        blocker.add(competitor)
        await blocker.flush()

        async def attempt() -> tuple[Payment, bool]:
            async with sessions() as session:
                return await create_payment(session, DATA, KEY)

        task = asyncio.create_task(attempt())
        await asyncio.sleep(0.3)
        assert not task.done(), "INSERT should wait on the unique index"

        await blocker.commit()
        payment, created = await task

    assert created is False
    assert payment.id == competitor.id
    assert await count_by_key(sessions) == 1
