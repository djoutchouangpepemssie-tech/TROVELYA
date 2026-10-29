"""Q24: the sliding 24 hours of the publication quota and its Retry-After."""

from datetime import UTC, datetime, timedelta

from trovelya.modules.catalog.service.publishing import retry_after

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _ago(*hours: float) -> list[datetime]:
    return sorted(NOW - timedelta(hours=h) for h in hours)


def test_under_the_limit_no_wait() -> None:
    assert retry_after(_ago(1, 2), 3, NOW) is None
    assert retry_after([], 1, NOW) is None


def test_at_the_limit_wait_for_the_oldest() -> None:
    assert retry_after(_ago(23, 1, 2), 3, NOW) == 3600


def test_over_the_limit_wait_until_enough_left() -> None:
    """61 in the window for a limit of 50 (the setting lowered): one more needs 12 to leave,
    the 12th oldest being an hour old, so 23 hours, not the hour of the oldest."""
    assert retry_after(_ago(23, *[1] * 60), 50, NOW) == 23 * 3600


def test_wait_rounded_up_to_the_second() -> None:
    assert retry_after([NOW - QUOTA + timedelta(milliseconds=1)], 1, NOW) == 1
    assert retry_after([NOW - timedelta(hours=23, milliseconds=500)], 1, NOW) == 3600


def test_limit_zero_freezes_publication() -> None:
    """The setting at 0 (or below) stops every putting online for a whole window, never a 500."""
    assert retry_after([], 0, NOW) == 24 * 3600
    assert retry_after(_ago(1), -1, NOW) == 24 * 3600


QUOTA = timedelta(hours=24)
