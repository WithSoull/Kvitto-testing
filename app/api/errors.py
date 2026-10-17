"""The only place where domain errors are translated into HTTP responses."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors import (
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


async def payment_not_found(_: Request, exc: PaymentNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Payment not found"}
    )


async def invalid_transition(_: Request, exc: InvalidTransitionError) -> JSONResponse:
    # The spec requires this exact body, without FastAPI's usual "detail" wrapper.
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"error": "invalid_transition"}
    )


async def unknown_tariff(_: Request, exc: UnknownTariffError) -> JSONResponse:
    return validation_error(
        ["body", "tariff_id"], "Unknown tariff", "unknown_tariff", exc.tariff_id
    )


async def unknown_promo_code(_: Request, exc: UnknownPromoCodeError) -> JSONResponse:
    return validation_error(
        ["body", "promo_code"], "Unknown promo code", "unknown_promo_code", exc.code
    )


async def idempotency_key_reused(_: Request, exc: IdempotencyKeyReusedError) -> JSONResponse:
    return validation_error(
        ["header", "Idempotency-Key"],
        "Idempotency key was already used with a different request",
        "idempotency_key_reused",
        exc.key,
    )


def register_error_handlers(app: FastAPI) -> None:
    # Starlette types handlers as accepting a bare Exception, so handlers narrowed to a
    # specific error class are rejected by mypy, although they are only ever called with it.
    app.add_exception_handler(PaymentNotFoundError, payment_not_found)  # type: ignore[arg-type]
    app.add_exception_handler(InvalidTransitionError, invalid_transition)  # type: ignore[arg-type]
    app.add_exception_handler(UnknownTariffError, unknown_tariff)  # type: ignore[arg-type]
    app.add_exception_handler(UnknownPromoCodeError, unknown_promo_code)  # type: ignore[arg-type]
    app.add_exception_handler(IdempotencyKeyReusedError, idempotency_key_reused)  # type: ignore[arg-type]
