from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.domain.enums import PaymentStatus


@pytest.fixture
async def payment_id(client: AsyncClient) -> str:
    response = await client.post(
        "/payments", json={"tariff_id": "basic", "email": "user@example.com", "method": "sbp"}
    )
    assert response.status_code == 201
    payment_id: str = response.json()["id"]
    return payment_id


async def send_webhook(client: AsyncClient, payment_id: str, status: str) -> Response:
    return await client.post("/webhooks/bank", json={"payment_id": payment_id, "status": status})


async def move_to(client: AsyncClient, payment_id: str, *statuses: str) -> None:
    for status in statuses:
        response = await send_webhook(client, payment_id, status)
        assert response.status_code == 200, response.json()


async def stored_status(session: AsyncSession, payment_id: str) -> PaymentStatus:
    # populate_existing: re-read the row instead of trusting the identity map.
    payment = await session.get(Payment, UUID(payment_id), populate_existing=True)
    assert payment is not None
    return payment.status


@pytest.mark.parametrize(
    ("history", "new_status"),
    [
        ((), "succeeded"),
        ((), "failed"),
        (("succeeded",), "refunded"),
    ],
)
async def test_allowed_transition(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_id: str,
    history: tuple[str, ...],
    new_status: str,
) -> None:
    await move_to(client, payment_id, *history)

    response = await send_webhook(client, payment_id, new_status)

    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
    assert await stored_status(db_session, payment_id) == new_status
    assert (await client.get(f"/payments/{payment_id}")).json()["status"] == new_status


@pytest.mark.parametrize(
    ("history", "new_status"),
    [
        ((), "refunded"),
        ((), "pending"),
        (("succeeded",), "failed"),
        (("succeeded",), "pending"),
        (("failed",), "succeeded"),
        (("failed",), "refunded"),
        (("succeeded", "refunded"), "succeeded"),
        (("succeeded", "refunded"), "pending"),
        # Same-status repeats are forbidden by design, see docs/DECISIONS.md.
        (("succeeded",), "succeeded"),
        (("failed",), "failed"),
        (("succeeded", "refunded"), "refunded"),
    ],
)
async def test_forbidden_transition_returns_409_and_keeps_status(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_id: str,
    history: tuple[str, ...],
    new_status: str,
) -> None:
    await move_to(client, payment_id, *history)
    status_before = await stored_status(db_session, payment_id)

    response = await send_webhook(client, payment_id, new_status)

    assert response.status_code == 409
    assert response.json() == {"error": "invalid_transition"}
    assert await stored_status(db_session, payment_id) == status_before


async def test_webhook_for_missing_payment_returns_404(client: AsyncClient) -> None:
    response = await send_webhook(client, str(uuid4()), "succeeded")

    assert response.status_code == 404
    assert response.json() == {"detail": "Payment not found"}


@pytest.mark.parametrize(
    "body",
    [
        {"payment_id": "not-a-uuid", "status": "succeeded"},
        {"status": "succeeded"},
        {"payment_id": str(uuid4())},
        {"payment_id": str(uuid4()), "status": "paid"},
    ],
)
async def test_webhook_validation_errors(client: AsyncClient, body: dict[str, Any]) -> None:
    response = await client.post("/webhooks/bank", json=body)

    assert response.status_code == 422
