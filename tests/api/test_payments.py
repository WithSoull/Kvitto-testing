from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from tests.helpers import LOOKALIKE_CODE, assert_validation_error

PAYMENT_FIELDS = {
    "id",
    "status",
    "tariff_id",
    "amount",
    "discount",
    "method",
    "installment_months",
    "schedule",
    "email",
    "created_at",
}


def payment_body(**overrides: Any) -> dict[str, Any]:
    return {"tariff_id": "standard", "email": "user@example.com", "method": "card"} | overrides


async def count_payments(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Payment)) or 0


async def load_payment(session: AsyncSession, payment_id: str) -> Payment:
    payment = await session.get(Payment, UUID(payment_id), populate_existing=True)
    assert payment is not None
    return payment


# --- Amounts and promo codes (spec scenario 1) ---


@pytest.mark.parametrize(
    ("tariff_id", "promo_code", "discount", "amount"),
    [
        ("basic", None, 0, 990000),
        ("standard", None, 0, 1990000),
        ("premium", None, 0, 2990000),
        ("basic", "KVITTO10", 99000, 891000),
        ("standard", "KVITTO10", 199000, 1791000),
        ("premium", "KVITTO10", 299000, 2691000),
        ("standard", "kvitto10", 199000, 1791000),
        ("standard", " KviTTo10 ", 199000, 1791000),
    ],
)
async def test_create_payment_amounts(
    client: AsyncClient,
    db_session: AsyncSession,
    tariff_id: str,
    promo_code: str | None,
    discount: int,
    amount: int,
) -> None:
    response = await client.post(
        "/payments", json=payment_body(tariff_id=tariff_id, promo_code=promo_code)
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == PAYMENT_FIELDS
    assert body["status"] == "pending"
    assert body["tariff_id"] == tariff_id
    assert (body["discount"], body["amount"]) == (discount, amount)
    assert body["method"] == "card"
    assert body["installment_months"] is None
    assert body["schedule"] is None
    datetime.fromisoformat(body["created_at"])

    stored = await load_payment(db_session, body["id"])
    assert (stored.discount, stored.amount) == (discount, amount)
    assert stored.promo_code == ("KVITTO10" if promo_code else None)


async def test_create_payment_normalizes_email(client: AsyncClient) -> None:
    response = await client.post("/payments", json=payment_body(email="  User@Example.COM "))

    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"


@pytest.mark.parametrize("promo_code", ["KVITTO99", LOOKALIKE_CODE])
async def test_create_payment_unknown_promo_code(
    client: AsyncClient, db_session: AsyncSession, promo_code: str
) -> None:
    response = await client.post("/payments", json=payment_body(promo_code=promo_code))

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["type"] == "unknown_promo_code"
    assert error["loc"] == ["body", "promo_code"]
    assert await count_payments(db_session) == 0


async def test_create_payment_unknown_tariff(client: AsyncClient, db_session: AsyncSession) -> None:
    response = await client.post("/payments", json=payment_body(tariff_id="gold"))

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["type"] == "unknown_tariff"
    assert error["loc"] == ["body", "tariff_id"]
    assert await count_payments(db_session) == 0


# --- Installments (spec scenario 2) ---


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("tariff_id", ["basic", "standard", "premium"])
@pytest.mark.parametrize("promo_code", [None, "KVITTO10"])
async def test_installment_schedule_sums_to_amount(
    client: AsyncClient,
    db_session: AsyncSession,
    months: int,
    tariff_id: str,
    promo_code: str | None,
) -> None:
    response = await client.post(
        "/payments",
        json=payment_body(
            tariff_id=tariff_id,
            method="installment",
            installment_months=months,
            promo_code=promo_code,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["installment_months"] == months
    assert len(body["schedule"]) == months
    assert sum(body["schedule"]) == body["amount"]
    assert max(body["schedule"]) - min(body["schedule"]) <= 1

    stored = await load_payment(db_session, body["id"])
    assert stored.schedule == body["schedule"]


async def test_installment_spec_example(client: AsyncClient) -> None:
    response = await client.post(
        "/payments", json=payment_body(method="installment", installment_months=3)
    )

    assert response.status_code == 201
    assert response.json()["amount"] == 1990000
    assert response.json()["schedule"] == [663334, 663333, 663333]


REQUIRED_MONTHS = "installment_months is required"
FORBIDDEN_MONTHS = "installment_months is allowed only for installment"


@pytest.mark.parametrize(
    ("overrides", "error_type", "loc", "msg_contains"),
    [
        # Cross-field rules come from the model validator, so their loc is the whole body.
        ({"method": "installment"}, "value_error", ["body"], REQUIRED_MONTHS),
        (
            {"method": "installment", "installment_months": None},
            "value_error",
            ["body"],
            REQUIRED_MONTHS,
        ),
        ({"method": "card", "installment_months": 3}, "value_error", ["body"], FORBIDDEN_MONTHS),
        ({"method": "sbp", "installment_months": 6}, "value_error", ["body"], FORBIDDEN_MONTHS),
        (
            {"method": "installment", "installment_months": 4},
            "literal_error",
            ["body", "installment_months"],
            "",
        ),
        ({"method": "cash"}, "enum", ["body", "method"], ""),
        ({"email": "not-an-email"}, "value_error", ["body", "email"], ""),
        ({"tariff_id": ""}, "string_too_short", ["body", "tariff_id"], ""),
    ],
)
async def test_create_payment_validation_errors(
    client: AsyncClient,
    db_session: AsyncSession,
    overrides: dict[str, Any],
    error_type: str,
    loc: list[str],
    msg_contains: str,
) -> None:
    response = await client.post("/payments", json=payment_body(**overrides))

    assert_validation_error(response, error_type, loc, msg_contains)
    assert await count_payments(db_session) == 0


@pytest.mark.parametrize("field", ["promocode", "promo", "installmentMonths", "amount"])
async def test_create_payment_rejects_unknown_fields(
    client: AsyncClient, db_session: AsyncSession, field: str
) -> None:
    # A typo like "promocode" must fail loudly instead of charging the full price.
    response = await client.post("/payments", json=payment_body(**{field: "KVITTO10"}))

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["type"] == "extra_forbidden"
    assert error["loc"] == ["body", field]
    assert await count_payments(db_session) == 0


# --- Idempotency (spec scenario 3) ---


async def test_repeated_idempotency_key_returns_same_payment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = {"Idempotency-Key": "order-42"}
    body = payment_body(method="installment", installment_months=6, promo_code="KVITTO10")

    first = await client.post("/payments", json=body, headers=headers)
    second = await client.post("/payments", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert await count_payments(db_session) == 1


async def test_repeated_idempotency_key_with_equivalent_body(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = {"Idempotency-Key": "order-43"}

    first = await client.post(
        "/payments", json=payment_body(promo_code="KVITTO10"), headers=headers
    )
    # Same request after normalization: promo code case and whitespace do not matter.
    second = await client.post(
        "/payments", json=payment_body(promo_code=" kvitto10"), headers=headers
    )

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["id"] == first.json()["id"]
    assert await count_payments(db_session) == 1


async def test_idempotency_key_reused_with_different_body(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = {"Idempotency-Key": "order-44"}

    first = await client.post("/payments", json=payment_body(tariff_id="basic"), headers=headers)
    second = await client.post("/payments", json=payment_body(tariff_id="premium"), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 422
    error = second.json()["detail"][0]
    assert error["type"] == "idempotency_key_reused"
    assert error["loc"] == ["header", "Idempotency-Key"]
    assert await count_payments(db_session) == 1
    stored = await load_payment(db_session, first.json()["id"])
    assert stored.tariff_id == "basic"


async def test_requests_without_idempotency_key_create_separate_payments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    first = await client.post("/payments", json=payment_body())
    second = await client.post("/payments", json=payment_body())

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert await count_payments(db_session) == 2


async def test_empty_idempotency_key_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/payments", json=payment_body(), headers={"Idempotency-Key": ""})

    assert_validation_error(response, "string_too_short", ["header", "Idempotency-Key"])


# --- Reading a payment (spec scenario 5) ---


async def test_get_payment(client: AsyncClient) -> None:
    created = await client.post(
        "/payments", json=payment_body(method="installment", installment_months=12)
    )

    response = await client.get(f"/payments/{created.json()['id']}")

    assert response.status_code == 200
    assert response.json() == created.json()


async def test_get_missing_payment_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/payments/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Payment not found"}


async def test_get_payment_with_invalid_id(client: AsyncClient) -> None:
    response = await client.get("/payments/not-a-uuid")

    assert_validation_error(response, "uuid_parsing", ["path", "payment_id"])
