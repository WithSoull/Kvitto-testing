import pytest

from app.domain.money import build_schedule, calc_discount

TARIFF_PRICES = [990000, 1990000, 2990000]
INSTALLMENT_MONTHS = [3, 6, 12]


@pytest.mark.parametrize(
    ("price", "percent", "expected"),
    [
        (990000, 10, 99000),
        (1990000, 10, 199000),
        (2990000, 10, 299000),
        (1990000, 0, 0),
        (1990000, 100, 1990000),
        # Not evenly divisible: the discount is floored, never more than promised.
        (999, 10, 99),
        (1, 10, 0),
    ],
)
def test_calc_discount(price: int, percent: int, expected: int) -> None:
    assert calc_discount(price, percent) == expected


@pytest.mark.parametrize(("price", "percent"), [(-1, 10), (1000, -1), (1000, 101)])
def test_calc_discount_rejects_invalid_input(price: int, percent: int) -> None:
    with pytest.raises(ValueError, match=r"price|percent"):
        calc_discount(price, percent)


def test_build_schedule_spec_example() -> None:
    assert build_schedule(1990000, 3) == [663334, 663333, 663333]


@pytest.mark.parametrize("months", INSTALLMENT_MONTHS)
@pytest.mark.parametrize("amount", [*TARIFF_PRICES, 891000, 1791000, 2691000, 1000001, 12, 13])
def test_build_schedule_invariants(amount: int, months: int) -> None:
    schedule = build_schedule(amount, months)

    assert sum(schedule) == amount
    assert len(schedule) == months
    # Leftover kopecks go to the first payments: values differ by at most 1, non-increasing.
    assert max(schedule) - min(schedule) <= 1
    assert schedule == sorted(schedule, reverse=True)


def test_build_schedule_puts_leftover_kopecks_first() -> None:
    assert build_schedule(1000002, 6) == [166667, 166667, 166667, 166667, 166667, 166667]
    assert build_schedule(1000004, 6) == [166668, 166668, 166667, 166667, 166667, 166667]


@pytest.mark.parametrize(("amount", "months"), [(1000, 0), (1000, -3), (0, 3), (11, 12)])
def test_build_schedule_rejects_invalid_input(amount: int, months: int) -> None:
    with pytest.raises(ValueError, match=r"amount|months"):
        build_schedule(amount, months)
