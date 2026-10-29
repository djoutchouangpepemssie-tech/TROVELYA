"""The prices a listing was shown at (P2-T08b, plan Q43): only while online, from its status
history; the lowest of the 30 days before a change, the change excluded (Omnibus)."""

from datetime import UTC, datetime, timedelta

import pytest

from trovelya.modules.catalog.service.prices import (
    lowest_price,
    online_periods,
    shown_prices,
)

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


CHANGES = [(_ago(60), 9000), (_ago(40), 8000), (_ago(20), 7000), (_ago(5), 9500)]
ALWAYS = [(_ago(60), None)]  # online since 60 days ago


def test_lowest_price_30_days() -> None:
    """The price of 40 days ago held until 20 days ago: it counts for the window's start."""
    assert lowest_price(CHANGES, ALWAYS, at=NOW) == 7000
    assert lowest_price(CHANGES, ALWAYS, at=_ago(21)) == 8000
    assert lowest_price(CHANGES, ALWAYS, at=NOW, days=4) == 9500


def test_new_price_never_its_own_reference() -> None:
    """A drop recorded exactly at `at`: the reference is what was shown before it."""
    assert lowest_price(CHANGES, ALWAYS, at=_ago(20)) == 8000


def test_lowest_price_counts_online_time_only() -> None:
    """Draft prices, and a whole window offline, are never the reference."""
    assert lowest_price(CHANGES, [(_ago(10), None)], at=NOW) == 7000
    assert lowest_price(CHANGES, [(_ago(3), None)], at=NOW) == 9500
    assert lowest_price(CHANGES, [], at=NOW) is None
    assert lowest_price(CHANGES, [(_ago(60), _ago(45))], at=NOW) is None


def test_price_changed_offline_counts_from_back_online() -> None:
    """Withdrawn at 9000 (J-50), the price lowered to 7000 offline (J-20), back online J-10."""
    periods = [(_ago(60), _ago(50)), (_ago(10), None)]
    changes = [(_ago(60), 9000), (_ago(20), 7000)]
    assert shown_prices(changes, periods) == [(_ago(60), 9000), (_ago(10), 7000)]
    assert lowest_price(changes, periods, at=_ago(11)) is None  # nothing shown in that window
    assert lowest_price(changes, periods, at=NOW, days=15) == 7000


def test_shown_prices_from_first_online() -> None:
    periods = [(_ago(30), None)]
    assert shown_prices(CHANGES, periods) == [(_ago(30), 8000), (_ago(20), 7000), (_ago(5), 9500)]
    assert shown_prices(CHANGES, []) == []
    back = [(_ago(60), _ago(50)), (_ago(45), None)]  # same price on both sides: shown once
    assert shown_prices([(_ago(60), 9000)], back) == [(_ago(60), 9000)]


def test_changes_at_the_same_instant_keep_their_order() -> None:
    same = [(_ago(10), 5000), (_ago(10), 4000)]
    assert shown_prices(same, [(_ago(5), None)]) == [(_ago(5), 4000)]


def test_online_periods_from_transitions() -> None:
    transitions = [
        (_ago(60), None, "draft"),
        (_ago(59), "draft", "active"),
        (_ago(50), "active", "withdrawn"),
        (_ago(40), "withdrawn", "pending_review"),
        (_ago(39), "pending_review", "active"),
    ]
    assert online_periods(transitions) == [(_ago(59), _ago(50)), (_ago(39), None)]


def test_naive_date_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        lowest_price(CHANGES, ALWAYS, at=NOW.replace(tzinfo=None))
