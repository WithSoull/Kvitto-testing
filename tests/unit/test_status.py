from itertools import product

import pytest

from app.domain.enums import PaymentStatus
from app.domain.errors import InvalidTransitionError
from app.domain.status import ensure_transition_allowed

ALLOWED = {
    (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
    (PaymentStatus.PENDING, PaymentStatus.FAILED),
    (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
}
FORBIDDEN = sorted(set(product(PaymentStatus, repeat=2)) - ALLOWED)


@pytest.mark.parametrize(("current", "new"), sorted(ALLOWED))
def test_allowed_transitions(current: PaymentStatus, new: PaymentStatus) -> None:
    ensure_transition_allowed(current, new)


# Includes same-status transitions (e.g. succeeded -> succeeded): forbidden by design,
# see docs/DECISIONS.md.
@pytest.mark.parametrize(("current", "new"), FORBIDDEN)
def test_forbidden_transitions(current: PaymentStatus, new: PaymentStatus) -> None:
    with pytest.raises(InvalidTransitionError) as exc_info:
        ensure_transition_allowed(current, new)

    assert (exc_info.value.current, exc_info.value.new) == (current, new)
