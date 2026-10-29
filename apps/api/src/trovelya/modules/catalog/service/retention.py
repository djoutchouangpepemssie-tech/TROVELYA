"""Daily purge of ended listings (P2-T04e, plan Q19, PII.md).

Deleted by the seller: erased `retention.deleted_listing_days` (30) after `deleted_at`.
Withdrawn or expired: `retention.ended_listing_days` (365) after the status was reached, if not
put back online. Removed by moderation: `retention.removed_listing_days` (180), the time to
contest (DSA art. 20). Sold listings keep a minimal record while an order points to them;
their content (`retention.sold_listing_days`) is purged with the orders of P4.

A listing goes with its photo links, favorites, price watches and histories; its photos are
deleted and leave storage at the media purge's next run, the brands its seller typed with
their last listing (E19). A listing removed by moderation then deleted by its seller keeps
the longer retention; reserved and sold ones wait for the orders of P4. Then the public
positions (Q20) no listing of their seller stands on, unless an address or a zone of the
seller is still there (Q28). A batch per transaction; a listing or a
seller busy right now is left for the next run. This job is a boundary: it commits.
"""

from datetime import datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.service.locations import REUSE_M
from trovelya.modules.identity.service import places_near
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

BATCH = 200
DEADLOCK = "40P01"
MAX_RETRIES = 3


async def _cutoffs(db: AsyncSession, now: datetime) -> dict[str, datetime]:
    """The thresholds of Q19; a retention of 0 days or less is a broken setting, refused rather
    than taken as « erase everything now »."""
    cutoffs: dict[str, datetime] = {}
    for name, key in (
        ("deleted", "retention.deleted_listing_days"),
        ("ended", "retention.ended_listing_days"),
        ("removed", "retention.removed_listing_days"),
    ):
        days = await repository.setting_int(db, key)
        if days < 1:
            raise ValueError(f"platform setting {key} must be at least 1 day, not {days}")
        cutoffs[f"{name}_before"] = now - timedelta(days=days)
    return cutoffs


async def _purge_batch(
    sessionmaker: async_sessionmaker[AsyncSession],
    cutoffs: dict[str, datetime],
    *,
    now: datetime,
    batch: int,
    after: UUID | None,
) -> tuple[list[UUID], int]:
    """(listings locked, listings erased) for one batch, in its own transaction; the batch
    starts after the listing `after`, so one kept on a second look is not taken again."""
    async with sessionmaker() as db:
        due = await repository.lock_listings_to_purge(db, cutoffs, limit=batch, after=after)
        erased = 0
        if due:
            erased, photos, brands = await repository.delete_purgeable(db, due, cutoffs)
            await listing_photos.discard_photos(db, photos, now=now)
            await repository.drop_unused_member_brands(db, brands)
        await commit(db)
    return due, erased


async def _purge_unused_places(
    sessionmaker: async_sessionmaker[AsyncSession], *, batch: int
) -> int:
    """Q20, Q28: the kept places no listing of their seller stands on and no address or zone
    of theirs lies near go; a seller drawing a position right now is left for the next run.
    Sellers by pages, one transaction each, one query for all the places of a seller."""
    deleted = 0
    after: UUID | None = None
    while True:
        async with sessionmaker() as db:
            sellers = await repository.sellers_with_unused_places(
                db, reuse_m=REUSE_M, after=after, limit=batch
            )
        for seller_id in sellers:
            async with sessionmaker() as db:
                if await repository.try_lock_seller_places(db, seller_id):
                    unused = await repository.unused_places(db, seller_id, reuse_m=REUSE_M)
                    kept = await places_near(
                        db, seller_id, [(p.lat, p.lon) for p in unused], radius_m=REUSE_M
                    )
                    gone = [p.id for i, p in enumerate(unused) if i not in kept]
                    await repository.delete_places(db, gone)
                    deleted += len(gone)
                await commit(db)
        if len(sellers) < batch:
            return deleted
        after = sellers[-1]


async def purge_ended_listings(
    sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock, batch: int = BATCH
) -> int:
    """The number of listings erased by this run. A batch caught in a deadlock (an account's
    erasure on the same listings) is rolled back and tried again, a few times at most."""
    now = clock.now()
    async with sessionmaker() as db:
        cutoffs = await _cutoffs(db, now)
    erased = 0
    retries = 0
    after: UUID | None = None
    while True:
        try:
            locked, gone = await _purge_batch(
                sessionmaker, cutoffs, now=now, batch=batch, after=after
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != DEADLOCK or retries >= MAX_RETRIES:
                raise
            retries += 1
            logger.warning("listings.purge_deadlock", retry=retries)
            continue
        erased += gone
        if len(locked) < batch:
            break
        after = max(locked)
    places = await _purge_unused_places(sessionmaker, batch=batch)
    logger.info("listings.purged", listings=erased, sellers_places=places)
    return erased
