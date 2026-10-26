"""Distance shown to a visitor (section 8.11, plan P2 point 6): never exact, rounded to the
nearest step, halves up."""

import pytest

from trovelya.modules.catalog.service.positions import round_distance


@pytest.mark.parametrize(
    ("meters", "shown"),
    [
        (0, "moins de 1 km"),
        (999, "moins de 1 km"),
        (1000, "1 km"),
        (1499, "1 km"),
        (1500, "2 km"),
        (9499, "9 km"),
        (9500, "10 km"),
        (9999, "10 km"),
        (10000, "10 km"),
        (12499, "10 km"),
        (12500, "15 km"),
        (99999, "100 km"),
        (100000, "100 km"),
        (104999, "100 km"),
        (105000, "110 km"),
    ],
)
def test_round_distance(meters: float, shown: str) -> None:
    assert round_distance(meters) == shown


@pytest.mark.parametrize("meters", [-1, float("nan"), float("inf")])
def test_round_distance_refuses_what_is_not_a_distance(meters: float) -> None:
    with pytest.raises(ValueError, match="distance"):
        round_distance(meters)
