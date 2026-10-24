from datetime import UTC, datetime, timedelta

import pytest

from trovelya.shared.clock import FixedClock, SystemClock
from trovelya.shared.ids import new_id


def test_uuid7_version() -> None:
    assert new_id().version == 7


def test_uuid7_monotonic() -> None:
    ids = [new_id() for _ in range(1000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 1000


def test_system_clock_is_utc_aware() -> None:
    now = SystemClock().now()
    assert now.tzinfo is UTC


def test_fixed_clock_advances() -> None:
    start = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
    clock = FixedClock(start)
    assert clock.now() == start
    clock.advance(timedelta(hours=48))
    assert clock.now() == start + timedelta(hours=48)


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        FixedClock(datetime(2026, 10, 23, 12, 0))  # noqa: DTZ001
