"""Money arithmetic. All amounts are integer kopecks; floats are never used."""


def calc_discount(price: int, percent: int) -> int:
    """Discount in kopecks, floored so it never exceeds the promised percent."""
    if price < 0:
        raise ValueError(f"price must be non-negative, got {price}")
    if not 0 <= percent <= 100:
        raise ValueError(f"percent must be within 0..100, got {percent}")
    return price * percent // 100


def build_schedule(amount: int, months: int) -> list[int]:
    """Split amount into equal monthly payments; leftover kopecks go to the first payments."""
    if months <= 0:
        raise ValueError(f"months must be positive, got {months}")
    if amount < months:
        raise ValueError(f"amount must be at least 1 kopeck per payment, got {amount}")
    base, remainder = divmod(amount, months)
    return [base + 1] * remainder + [base] * (months - remainder)
