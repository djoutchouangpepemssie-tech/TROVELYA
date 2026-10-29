"""Quotas over a rolling window (plan P2 Q24, Q45): how long until one more is allowed."""

import math
from datetime import datetime, timedelta

DAY = timedelta(hours=24)


def retry_after(
    times: list[datetime], limit: int, now: datetime, window: timedelta = DAY
) -> int | None:
    """None while fewer than `limit` of `times` (oldest first) fall in the window; else the
    seconds until enough of them leave it for one more (the whole window when the limit is 0:
    frozen)."""
    if limit <= 0:
        return int(window.total_seconds())
    if len(times) < limit:
        return None
    leaving = times[len(times) - limit]  # the oldest that must leave
    return max(1, math.ceil((leaving + window - now).total_seconds()))
