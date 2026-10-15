from collections.abc import Mapping
from typing import Final

from app.domain.errors import UnknownPromoCodeError

# Normalized (upper-case) code -> discount percent.
PROMO_CODES: Final[Mapping[str, int]] = {"KVITTO10": 10}


def normalize_promo_code(raw: str | None) -> str | None:
    """Case-insensitive codes: trim and upper-case; blank means no code."""
    if raw is None:
        return None
    code = raw.strip().upper()
    return code or None


def promo_discount_percent(code: str | None) -> int:
    """Discount percent for a normalized code; 0 when no code is given."""
    if code is None:
        return 0
    try:
        return PROMO_CODES[code]
    except KeyError:
        raise UnknownPromoCodeError(code) from None
