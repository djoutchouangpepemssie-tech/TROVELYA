"""The prices a listing was shown at (P2-T08, section 7.5 `listing_price_history`, plan Q43).

Only what was shown online counts: from the first time the listing went online, the price of
that moment, then each change. A price tried in the draft stays the seller's own. The lowest
price of the 30 days before a date is the reference of a struck-through price (Omnibus, P10)."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.catalog import repository
from trovelya.modules.identity.service import shown_sellers

Change = tuple[datetime, int]  # when, the new price in minor units


def shown_prices(changes: Sequence[Change], *, online_since: datetime | None) -> list[Change]:
    """The price at the first time online (dated then), then each later change; none before."""
    if online_since is None:
        return []
    ordered = sorted(changes)
    before = [price for at, price in ordered if at <= online_since]
    shown: list[Change] = [(online_since, before[-1])] if before else []
    return shown + [(at, price) for at, price in ordered if at > online_since]


def lowest_price(
    changes: Sequence[Change], *, online_since: datetime | None, at: datetime, days: int = 30
) -> int | None:
    """The lowest price shown in the `days` before `at` (the one in force at the window's start
    included); None when the listing was never online by then."""
    if online_since is None or online_since > at:
        return None
    start = max(at - timedelta(days=days), online_since)
    shown = [(when, price) for when, price in shown_prices(changes, online_since=online_since)]
    in_force = [price for when, price in shown if when <= start][-1:]
    during = [price for when, price in shown if start < when <= at]
    prices = in_force + during
    return min(prices) if prices else None


async def lowest_price_30_days(db: AsyncSession, listing_id: UUID, at: datetime) -> int | None:
    """Omnibus: the reference price of a struck-through price on `listing_id` at `at`."""
    changes, online_since = await repository.price_changes(db, listing_id)
    return lowest_price(changes, online_since=online_since, at=at)


async def price_history(db: AsyncSession, listing_id: UUID) -> tuple[str, list[Change]]:
    """The prices of a listing online, for anybody; 404 for any other (as if it did not exist)."""
    row = await repository.favorite_target(db, listing_id)
    if row is None or row.status != "active" or not await shown_sellers(db, [row.seller_id]):
        raise AppError(ErrorCode.NOT_FOUND, 404)
    changes, online_since = await repository.price_changes(db, listing_id)
    return row.currency, shown_prices(changes, online_since=online_since)
