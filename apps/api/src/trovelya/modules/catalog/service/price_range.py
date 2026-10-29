"""The price range the AI help proposes (P2-T06a3a, plan Q44): from the prices of the
comparable listings online, the 25th to the 75th percentile, interpolated between ranks (as
PostgreSQL's `percentile_cont`), rounded half up to the euro; none under 5 comparables."""

from collections.abc import Sequence
from fractions import Fraction

MIN_COMPARABLES = 5
COMPARABLES = 20  # the nearest by embedding (Q44)
EURO = 100  # minor units


def _percentile(ordered: Sequence[int], share: Fraction) -> Fraction:
    position = share * (len(ordered) - 1)
    below = int(position)
    above = min(below + 1, len(ordered) - 1)
    return ordered[below] + (position - below) * (ordered[above] - ordered[below])


def _to_euro(amount: Fraction) -> int:
    """Half up, exactly (no float, no banker's rounding)."""
    return int((amount / EURO + Fraction(1, 2)) // 1) * EURO


def price_range(prices: Sequence[int]) -> tuple[int, int] | None:
    """(low, high) in minor units, or None under `MIN_COMPARABLES` prices."""
    if len(prices) < MIN_COMPARABLES:
        return None
    ordered = sorted(prices)
    low, high = (_percentile(ordered, Fraction(q, 4)) for q in (1, 3))
    return _to_euro(low), _to_euro(high)
