from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.domain.enums import PaymentMethod, PaymentStatus
from tests.helpers import assert_validation_error

BASE_TIME = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
async def payments(db_session: AsyncSession) -> list[Payment]:
    """Five payments, created one minute apart (index 0 is the oldest).

    created_at is set explicitly: within one transaction now() returns the same
    timestamp, so server defaults would make the ordering ambiguous.
    """
    rows = [
        ("anna@example.com", PaymentStatus.PENDING),
        ("anna@example.com", PaymentStatus.SUCCEEDED),
        ("boris@example.com", PaymentStatus.SUCCEEDED),
        ("anna@example.com", PaymentStatus.FAILED),
        ("boris@example.com", PaymentStatus.PENDING),
    ]
    created = [
        Payment(
            tariff_id="basic",
            email=email,
            status=status,
            method=PaymentMethod.CARD,
            price=990000,
            discount=0,
            amount=990000,
            created_at=BASE_TIME + timedelta(minutes=index),
        )
        for index, (email, status) in enumerate(rows)
    ]
    db_session.add_all(created)
    await db_session.flush()
    return created


def ids(payments: list[Payment], *indexes: int) -> list[str]:
    return [str(payments[index].id) for index in indexes]


async def list_ids(client: AsyncClient, **params: Any) -> list[str]:
    response = await client.get("/payments", params=params)
    assert response.status_code == 200, response.json()
    return [payment["id"] for payment in response.json()]


async def test_list_returns_newest_first(client: AsyncClient, payments: list[Payment]) -> None:
    response = await client.get("/payments")

    assert response.status_code == 200
    body = response.json()
    assert [payment["id"] for payment in body] == ids(payments, 4, 3, 2, 1, 0)
    assert set(body[0]) == {
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


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"email": "anna@example.com"}, (3, 1, 0)),
        # Emails are stored lower-cased, the filter is case-insensitive.
        ({"email": " Anna@Example.COM "}, (3, 1, 0)),
        ({"status": "succeeded"}, (2, 1)),
        ({"status": "pending"}, (4, 0)),
        ({"email": "anna@example.com", "status": "succeeded"}, (1,)),
        ({"email": "boris@example.com", "status": "failed"}, ()),
        ({"email": "nobody@example.com"}, ()),
        ({"status": "refunded"}, ()),
    ],
)
async def test_list_filters(
    client: AsyncClient, payments: list[Payment], params: dict[str, str], expected: tuple[int, ...]
) -> None:
    assert await list_ids(client, **params) == ids(payments, *expected)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"limit": 2}, (4, 3)),
        ({"limit": 2, "offset": 2}, (2, 1)),
        ({"limit": 2, "offset": 4}, (0,)),
        ({"offset": 5}, ()),
        ({"email": "anna@example.com", "limit": 1, "offset": 1}, (1,)),
    ],
)
async def test_list_pagination(
    client: AsyncClient, payments: list[Payment], params: dict[str, Any], expected: tuple[int, ...]
) -> None:
    assert await list_ids(client, **params) == ids(payments, *expected)


@pytest.mark.parametrize(
    ("params", "error_type", "loc"),
    [
        ({"limit": 0}, "greater_than_equal", ["query", "limit"]),
        ({"limit": 101}, "less_than_equal", ["query", "limit"]),
        ({"offset": -1}, "greater_than_equal", ["query", "offset"]),
        ({"status": "paid"}, "enum", ["query", "status"]),
        ({"limit": "many"}, "int_parsing", ["query", "limit"]),
    ],
)
async def test_list_rejects_invalid_params(
    client: AsyncClient, params: dict[str, Any], error_type: str, loc: list[str]
) -> None:
    response = await client.get("/payments", params=params)

    assert_validation_error(response, error_type, loc)
