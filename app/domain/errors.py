from uuid import UUID

from app.domain.enums import PaymentStatus


class DomainError(Exception):
    """Base class for business rule violations; mapped to HTTP in app/api/errors.py."""


class UnknownTariffError(DomainError):
    def __init__(self, tariff_id: str) -> None:
        super().__init__(f"Unknown tariff: {tariff_id!r}")
        self.tariff_id = tariff_id


class UnknownPromoCodeError(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__(f"Unknown promo code: {code!r}")
        self.code = code


class PaymentNotFoundError(DomainError):
    def __init__(self, payment_id: UUID) -> None:
        super().__init__(f"Payment not found: {payment_id}")
        self.payment_id = payment_id


class InvalidTransitionError(DomainError):
    def __init__(self, current: PaymentStatus, new: PaymentStatus) -> None:
        super().__init__(f"Transition {current} -> {new} is not allowed")
        self.current = current
        self.new = new


class IdempotencyKeyReusedError(DomainError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Idempotency key {key!r} was already used with a different request")
        self.key = key
