"""The price range the AI help proposes (P2-T06a3a, plan Q44): the 25th to 75th percentile of
the comparable prices, in whole euros, only from 5 comparables."""

import pytest

from trovelya.modules.catalog.service.price_range import MIN_COMPARABLES, price_range


def test_no_range_under_five_comparables() -> None:
    assert MIN_COMPARABLES == 5
    assert price_range([1000, 2000, 3000, 4000]) is None
    assert price_range([]) is None


def test_quartiles_interpolated_then_rounded_to_the_euro() -> None:
    """Linear interpolation between ranks (as PostgreSQL's percentile_cont), the order of the
    prices given never matters."""
    assert price_range([5000, 1000, 3000, 2000, 4000]) == (2000, 4000)
    # Ranks 1.5 and 4.5 (from 0) of 7: 2250 + 0.5 * 1000 = 2750, 4750 + 0.5 * 1000 = 5250;
    # 27.50 € and 52.50 € round half up.
    assert price_range([1250, 2250, 3250, 4250, 4750, 5750, 6750]) == (2800, 5300)


@pytest.mark.parametrize(
    ("prices", "expected"),
    [
        ([1050] * 5, (1100, 1100)),  # 10.50 € rounds half up
        ([1049] * 5, (1000, 1000)),
        ([150] * 5, (200, 200)),
    ],
)
def test_half_up_to_the_euro(prices: list[int], expected: tuple[int, int]) -> None:
    assert price_range(prices) == expected
