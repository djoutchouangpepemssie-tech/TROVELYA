"""The prices a listing was shown at (P2-T08b, section 7.5 `listing_price_history`, plan Q43).

Only what was shown online counts: the listing's periods online come from its status history;
in each, the price in force when it went (back) online, dated then, then each change made while
online. A price set offline (in the draft, withdrawn, awaiting review) is shown only from the
next time online, if ever. The reference of a struck-through price (Omnibus, P10) is the lowest
price shown in the 30 days before the change, the change's instant excluded; 30 days are
counted as 720 hours (UTC)."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.catalog import repository
from trovelya.modules.identity.service import shown_sellers

Change = tuple[datetime, int]  # when, the new price in minor units, in the order recorded
Period = tuple[datetime, datetime | None]  # online from, until (None: still online)
Transition = tuple[datetime, str | None, str]  # when, from status, to status
ONLINE = frozenset({"active"})
NIL_ID = UUID(int=0)


def online_periods(transitions: Sequence[Transition]) -> list[Period]:
    periods: list[Period] = []
    start: datetime | None = None
    for at, _, to_status in transitions:
        if to_status in ONLINE and start is None:
            start = at
        elif to_status not in ONLINE and start is not None:
            periods.append((start, at))
            start = None
    return periods + ([(start, None)] if start is not None else [])


def _in_force(changes: Sequence[Change], at: datetime) -> int | None:
    """The price in force at `at` (the last one recorded at or before it)."""
    found = None
    for when, price in changes:
        if when > at:
            break
        found = price
    return found


def shown_prices(changes: Sequence[Change], periods: Sequence[Period]) -> list[Change]:
    """Each price as it was shown: at the start of each period online, then each change during
    it; a price unchanged across a period offline is not repeated."""
    shown: list[Change] = []
    for start, end in periods:
        opening = _in_force(changes, start)
        points = [] if opening is None else [(start, opening)]
        points += [(w, p) for w, p in changes if start < w and (end is None or w < end)]
        for point in points:
            if not shown or shown[-1][1] != point[1]:
                shown.append(point)
    return shown


def lowest_price(
    changes: Sequence[Change], periods: Sequence[Period], *, at: datetime, days: int = 30
) -> int | None:
    """The lowest price shown in the `days` before `at`, `at` itself excluded (the new price is
    never its own reference); None when nothing was shown then."""
    if at.tzinfo is None:
        raise ValueError("`at` must carry its time zone")
    window = at - timedelta(days=days)
    prices: list[int] = []
    for start, end in periods:
        low, high = max(start, window), at if end is None else min(end, at)
        if low >= high:
            continue
        opening = _in_force(changes, low)
        prices += [] if opening is None else [opening]
        prices += [p for w, p in changes if low < w < high]
    return min(prices) if prices else None


async def _facts(db: AsyncSession, listing_id: UUID) -> tuple[list[Change], list[Period]]:
    changes, transitions = await repository.price_facts(db, listing_id)
    return changes, online_periods(transitions)


async def lowest_price_30_days(db: AsyncSession, listing_id: UUID, at: datetime) -> int | None:
    """Omnibus: the reference price of a struck-through price set on `listing_id` at `at`."""
    changes, periods = await _facts(db, listing_id)
    return lowest_price(changes, periods, at=at)


async def price_history(db: AsyncSession, listing_id: UUID) -> tuple[str, list[Change]]:
    """The prices of a listing online, for anybody; 404 for any other (as if it did not exist).
    The seller is read whatever the listing: every 404 costs the same queries."""
    row = await repository.listing_state(db, listing_id)
    online = row is not None and row.status in ONLINE
    shown = await shown_sellers(db, [row.seller_id if row and online else NIL_ID])
    if row is None or not online or not shown:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    changes, periods = await _facts(db, listing_id)
    return row.currency, shown_prices(changes, periods)
