import pytest

from app.domain.errors import UnknownPromoCodeError
from app.domain.promo import normalize_promo_code, promo_discount_percent


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("KVITTO10", "KVITTO10"),
        ("kvitto10", "KVITTO10"),
        (" KviTTo10 ", "KVITTO10"),
        ("unknown", "UNKNOWN"),
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


def test_promo_discount_percent_unknown_code() -> None:
    with pytest.raises(UnknownPromoCodeError) as exc_info:
        promo_discount_percent("KVITTO99")

    assert exc_info.value.code == "KVITTO99"
