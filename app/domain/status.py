from collections.abc import Mapping
from typing import Final

from app.domain.enums import PaymentStatus
from app.domain.errors import InvalidTransitionError

ALLOWED_TRANSITIONS: Final[Mapping[PaymentStatus, frozenset[PaymentStatus]]] = {
    PaymentStatus.PENDING: frozenset({PaymentStatus.SUCCEEDED, PaymentStatus.FAILED}),
    PaymentStatus.SUCCEEDED: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


def ensure_transition_allowed(current: PaymentStatus, new: PaymentStatus) -> None:
    # Same-status transitions are rejected too: the spec allows only the listed ones.
    if new not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(current, new)
