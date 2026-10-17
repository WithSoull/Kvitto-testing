import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.domain.enums import PaymentStatus
from tests.helpers import assert_validation_error, post_webhook, sign


@pytest.fixture
async def payment_id(client: AsyncClient) -> str:
    response = await client.post(
        "/payments", json={"tariff_id": "basic", "email": "user@example.com", "method": "sbp"}
    )
    assert response.status_code == 201
    payment_id: str = response.json()["id"]
    return payment_id


async def send_webhook(client: AsyncClient, payment_id: str, status: str) -> Response:
    return await post_webhook(client, {"payment_id": payment_id, "status": status})


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
    ("body", "error_type", "loc"),
    [
        (
            {"payment_id": "not-a-uuid", "status": "succeeded"},
            "uuid_parsing",
            ["body", "payment_id"],
        ),
        ({"status": "succeeded"}, "missing", ["body", "payment_id"]),
        ({"payment_id": str(uuid4())}, "missing", ["body", "status"]),
        ({"payment_id": str(uuid4()), "status": "paid"}, "enum", ["body", "status"]),
    ],
)
async def test_webhook_validation_errors(
    client: AsyncClient, body: dict[str, Any], error_type: str, loc: list[str]
) -> None:
    response = await post_webhook(client, body)

    assert_validation_error(response, error_type, loc)


async def test_webhook_tolerates_unknown_fields(
    client: AsyncClient, db_session: AsyncSession, payment_id: str
) -> None:
    # The bank may add fields to its notifications; that must not break status updates.
    body = {"payment_id": payment_id, "status": "succeeded", "event_id": "evt_1", "amount": 1}

    response = await post_webhook(client, body)

    assert response.status_code == 200
    assert await stored_status(db_session, payment_id) == PaymentStatus.SUCCEEDED


# --- Signature (bonus): X-Signature = hex HMAC-SHA256 of the raw body with WEBHOOK_SECRET ---


@pytest.mark.parametrize(
    "signature",
    [
        None,
        "",
        "0" * 64,
        sign(b"some other body"),
        sign(b"{}", secret="wrong-secret"),
        "не-hex-подпись",
    ],
)
async def test_invalid_signature_returns_401_and_keeps_status(
    client: AsyncClient, db_session: AsyncSession, payment_id: str, signature: str | None
) -> None:
    response = await post_webhook(
        client, {"payment_id": payment_id, "status": "succeeded"}, signature=signature
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid signature"}
    assert await stored_status(db_session, payment_id) == PaymentStatus.PENDING


async def test_signature_is_checked_over_raw_bytes(
    client: AsyncClient, db_session: AsyncSession, payment_id: str
) -> None:
    # Unusual formatting: a server that re-serializes JSON before hashing would reject this.
    body = f'{{ "status" : "succeeded",\n  "payment_id":"{payment_id}" }}'.encode()

    response = await post_webhook(client, body)

    assert response.status_code == 200
    assert await stored_status(db_session, payment_id) == PaymentStatus.SUCCEEDED


async def test_tampered_body_is_rejected(client: AsyncClient, payment_id: str) -> None:
    signed = json.dumps({"payment_id": payment_id, "status": "failed"}).encode()
    tampered = signed.replace(b"failed", b"succeeded")

    response = await post_webhook(client, tampered, signature=sign(signed))

    assert response.status_code == 401


async def test_signature_is_checked_before_body_validation(client: AsyncClient) -> None:
    # An unauthenticated caller must not learn anything from validation errors.
    response = await post_webhook(client, {"status": "paid"}, signature="0" * 64)

    assert response.status_code == 401
