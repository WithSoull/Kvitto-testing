import pytest

from app.domain.errors import UnknownPromoCodeError
from app.domain.promo import normalize_promo_code, promo_discount_percent
from tests.helpers import LOOKALIKE_CODE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("KVITTO10", "KVITTO10"),
        ("kvitto10", "KVITTO10"),
        (" KviTTo10 ", "KVITTO10"),
        ("unknown", "UNKNOWN"),
        # Non-ASCII is left as is: Unicode upper() maps the dotless i to "I",
        # which would turn a look-alike code into a valid one.
        (LOOKALIKE_CODE, LOOKALIKE_CODE),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_promo_code(raw: str | None, expected: str | None) -> None:
    assert normalize_promo_code(raw) == expected


@pytest.mark.parametrize(("code", "expected"), [(None, 0), ("KVITTO10", 10)])
def test_promo_discount_percent(code: str | None, expected: int) -> None:
    assert promo_discount_percent(code) == expected


@pytest.mark.parametrize("raw", ["KVITTO99", LOOKALIKE_CODE])
def test_promo_discount_percent_unknown_code(raw: str) -> None:
    code = normalize_promo_code(raw)

    with pytest.raises(UnknownPromoCodeError) as exc_info:
        promo_discount_percent(code)

    assert exc_info.value.code == raw
