"""Daily purge of ended listings (P2-T04e, plan Q19, PII.md).

Deleted by the seller: erased `retention.deleted_listing_days` (30) after `deleted_at`.
Withdrawn or expired: `retention.ended_listing_days` (365) after the status was reached, if not
put back online. Removed by moderation: `retention.removed_listing_days` (180), the time to
contest (DSA art. 20). Sold listings keep a minimal record while an order points to them; their
content (`retention.sold_listing_days`) is purged with the orders of P4.

A listing goes with its photo links, favorites, price watches and histories; its photos are
deleted and leave storage at the media purge's next run. Then the public positions (Q20) no
listing of their seller stands on. A batch per transaction; a listing or a seller busy right
now is left for the next run. This job is a boundary: it commits.
"""

from datetime import timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.service.locations import REUSE_M
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

BATCH = 200


async def purge_ended_listings(
    sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock, batch: int = BATCH
) -> int:
    """The number of listings erased by this run."""
    now = clock.now()
    async with sessionmaker() as db:
        cutoffs = {
            f"{name}_before": now - timedelta(days=await repository.setting_int(db, key))
            for name, key in (
                ("deleted", "retention.deleted_listing_days"),
                ("ended", "retention.ended_listing_days"),
                ("removed", "retention.removed_listing_days"),
            )
        }
    erased = 0
    while True:
        async with sessionmaker() as db:
            due = await repository.lock_listings_to_purge(db, cutoffs, limit=batch)
            if due:
                photos = await repository.photos_of(db, due)
                await repository.delete_listings(db, due)
                await listing_photos.discard_photos(db, photos, now=now)
            await commit(db)
        erased += len(due)
        if len(due) < batch:
            break
    places = 0
    async with sessionmaker() as db:
        sellers = await repository.sellers_with_unused_places(db, reuse_m=REUSE_M)
    for seller_id in sellers:
        async with sessionmaker() as db:
            places += await repository.delete_unused_places(db, seller_id, reuse_m=REUSE_M)
            await commit(db)
    logger.info("listings.purged", listings=erased, sellers_places=places)
    return erased
