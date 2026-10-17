from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response, status

from app.api.deps import SessionDep
from app.domain.enums import PaymentStatus
from app.schemas.errors import ErrorDetail
from app.schemas.payment import PaymentCreate, PaymentOut
from app.services import payments as payments_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment",
    description=(
        "Creates a payment in `pending` status. With an `Idempotency-Key` header, "
        "a repeated request returns the existing payment with 200 instead of creating "
        "a new one; the same key with a different body is rejected with 422."
    ),
    responses={
        status.HTTP_200_OK: {
            "model": PaymentOut,
            "description": "Payment already created with this Idempotency-Key",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "Validation error, unknown tariff, unknown promo code, "
                "or Idempotency-Key reused with a different body"
            ),
        },
    },
)
async def create_payment(
    body: PaymentCreate,
    session: SessionDep,
    response: Response,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> PaymentOut:
    payment, created = await payments_service.create_payment(session, body, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
    return PaymentOut.model_validate(payment)


@router.get(
    "",
    response_model=list[PaymentOut],
    status_code=status.HTTP_200_OK,
    summary="List payments",
    description="Newest first. Filters are combined with AND; email matching is case-insensitive.",
)
async def list_payments(
    session: SessionDep,
    email: Annotated[str | None, Query(max_length=320, examples=["user@example.com"])] = None,
    # Exposed as ?status=...; the Python name avoids shadowing fastapi.status.
    payment_status: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PaymentOut]:
    payments = await payments_service.list_payments(
        session, email=email, status=payment_status, limit=limit, offset=offset
    )
    return [PaymentOut.model_validate(payment) for payment in payments]


@router.get(
    "/{payment_id}",
    response_model=PaymentOut,
    status_code=status.HTTP_200_OK,
    summary="Get a payment",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorDetail, "description": "Not found"}},
)
async def get_payment(payment_id: UUID, session: SessionDep) -> PaymentOut:
    payment = await payments_service.get_payment(session, payment_id)
    return PaymentOut.model_validate(payment)
