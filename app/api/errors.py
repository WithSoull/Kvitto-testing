"""The only place where domain errors are translated into HTTP responses."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors import (
    DomainError,
    IdempotencyKeyReusedError,
    InvalidTransitionError,
    PaymentNotFoundError,
    UnknownPromoCodeError,
    UnknownTariffError,
)


def validation_error(loc: list[str], msg: str, error_type: str, value: Any) -> JSONResponse:
    """A business 422 in the same shape as FastAPI's own validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": [{"type": error_type, "loc": loc, "msg": msg, "input": value}]},
    )


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # One handler for the DomainError base class keeps the whole mapping in one place
    # and matches the (Request, Exception) signature Starlette expects, so mypy accepts it.
    match exc:
        case PaymentNotFoundError():
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Payment not found"}
            )
        case InvalidTransitionError():
            # The spec requires this exact body, without FastAPI's usual "detail" wrapper.
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT, content={"error": "invalid_transition"}
            )
        case UnknownTariffError():
            return validation_error(
                ["body", "tariff_id"], "Unknown tariff", "unknown_tariff", exc.tariff_id
            )
        case UnknownPromoCodeError():
            return validation_error(
                ["body", "promo_code"], "Unknown promo code", "unknown_promo_code", exc.code
            )
        case IdempotencyKeyReusedError():
            return validation_error(
                ["header", "Idempotency-Key"],
                "Idempotency key was already used with a different request",
                "idempotency_key_reused",
                exc.key,
            )
    # A new DomainError without a mapping is a bug: surface it as a 500, not a silent 200.
    raise exc


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
