"""The prices a listing was shown at (P2-T08, plan Q43): from its first time online, the price
of that moment then each change; the lowest of the 30 days before a date (Omnibus)."""

from datetime import UTC, datetime, timedelta

from trovelya.modules.catalog.service.prices import lowest_price, shown_prices

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


CHANGES = [(_ago(60), 9000), (_ago(40), 8000), (_ago(20), 7000), (_ago(5), 9500)]


def test_lowest_price_30_days() -> None:
    """Changes 40, 20 and 5 days ago: the price of 40 days ago held until 20 days ago, so it
    counts for the start of the window."""
    assert lowest_price(CHANGES, online_since=_ago(60), at=NOW, days=30) == 7000
    assert lowest_price(CHANGES, online_since=_ago(60), at=_ago(21), days=30) == 8000
    assert lowest_price(CHANGES, online_since=_ago(60), at=NOW, days=4) == 9500


def test_lowest_price_counts_online_time_only() -> None:
    """A price tried in the draft, before the first time online, is never the reference."""
    assert lowest_price(CHANGES, online_since=_ago(10), at=NOW, days=30) == 7000
    assert lowest_price(CHANGES, online_since=_ago(3), at=NOW, days=30) == 9500
    assert lowest_price(CHANGES, online_since=None, at=NOW, days=30) is None


def test_shown_prices_from_first_online() -> None:
    assert shown_prices(CHANGES, online_since=_ago(30)) == [
        (_ago(30), 8000),
        (_ago(20), 7000),
        (_ago(5), 9500),
    ]
    assert shown_prices(CHANGES, online_since=None) == []
    assert shown_prices([(_ago(10), 4000)], online_since=_ago(10)) == [(_ago(10), 4000)]
