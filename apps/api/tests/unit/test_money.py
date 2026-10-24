from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trovelya.shared.money import (
    CurrencyMismatchError,
    Money,
    ceil_div,
    floor_div,
    percent_bp_ceil,
    percent_bp_floor,
)

amounts = st.integers(min_value=0, max_value=10**12)
basis_points = st.integers(min_value=0, max_value=10_000)


@pytest.mark.parametrize("bad", [1.0, True, Decimal("1"), "1", None])
def test_rejects_non_int_amount(bad: object) -> None:
    with pytest.raises(TypeError):
        Money(bad, "EUR")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["eur", "EURO", "EU", "€€€", ""])
def test_rejects_bad_currency(bad: str) -> None:
    with pytest.raises(ValueError, match="currency"):
        Money(100, bad)


def test_currency_mismatch_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        _ = Money(100, "EUR") + Money(100, "PLN")
    with pytest.raises(CurrencyMismatchError):
        _ = Money(100, "EUR") - Money(100, "PLN")
    with pytest.raises(CurrencyMismatchError):
        assert Money(100, "EUR") < Money(100, "PLN")


def test_add_sub_same_currency() -> None:
    assert Money(1000, "EUR") + Money(250, "EUR") == Money(1250, "EUR")
    assert Money(1000, "EUR") - Money(1250, "EUR") == Money(-250, "EUR")


def test_ordering_same_currency() -> None:
    assert Money(100, "EUR") < Money(101, "EUR")
    assert Money(101, "EUR") >= Money(101, "EUR")


def test_money_is_immutable() -> None:
    money = Money(100, "EUR")
    with pytest.raises(AttributeError):
        money.amount_minor = 200  # type: ignore[misc]


def test_zero() -> None:
    assert Money.zero("EUR") == Money(0, "EUR")


def test_percent_bp_ceil_rounds_up() -> None:
    # Section 8.1: 5 % of 18,99 € = 0,9495 € → 0,95 € (buyer fee, rounded up).
    assert percent_bp_ceil(Money(1899, "EUR"), 500) == Money(95, "EUR")


def test_percent_bp_floor_rounds_down() -> None:
    # Amount paid out: rounded down, in favour of the seller (section 8.2).
    assert percent_bp_floor(Money(1899, "EUR"), 500) == Money(94, "EUR")


def test_percent_exact_values() -> None:
    assert percent_bp_ceil(Money(24000, "EUR"), 500) == Money(1200, "EUR")
    assert percent_bp_floor(Money(50000, "EUR"), 800) == Money(4000, "EUR")


def test_percent_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="basis points"):
        percent_bp_ceil(Money(100, "EUR"), -1)
    with pytest.raises(ValueError, match="basis points"):
        percent_bp_floor(Money(100, "EUR"), 10_001)
    with pytest.raises(ValueError, match="negative"):
        percent_bp_ceil(Money(-100, "EUR"), 100)
    with pytest.raises(TypeError):
        percent_bp_floor(Money(100, "EUR"), 1.5)  # type: ignore[arg-type]


def test_divisions_reject_non_positive_denominator() -> None:
    with pytest.raises(ValueError, match="denominator"):
        ceil_div(1, 0)
    with pytest.raises(ValueError, match="denominator"):
        floor_div(1, -2)


@given(amounts, basis_points)
def test_ceil_ge_floor(amount: int, bp: int) -> None:
    money = Money(amount, "EUR")
    assert percent_bp_ceil(money, bp) >= percent_bp_floor(money, bp)


@given(amounts, basis_points)
def test_ceil_minus_floor_le_1(amount: int, bp: int) -> None:
    money = Money(amount, "EUR")
    diff = percent_bp_ceil(money, bp) - percent_bp_floor(money, bp)
    assert diff.amount_minor in (0, 1)


@given(
    st.integers(min_value=-(10**12), max_value=10**12), st.integers(min_value=1, max_value=10**6)
)
def test_ceil_div_exact(numerator: int, denominator: int) -> None:
    result = ceil_div(numerator, denominator)
    assert result * denominator >= numerator > (result - 1) * denominator
    assert floor_div(numerator, denominator) * denominator <= numerator
