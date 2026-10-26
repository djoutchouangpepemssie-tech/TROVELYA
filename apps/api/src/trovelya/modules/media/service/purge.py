"""Daily purge of media files and rows (P2-T02c2, ADR-0019).

- An erased account's photos: at once (the eraser has hidden them during the erasure).
- A deleted photo (avatar replaced or removed, photo withdrawn): after 30 days.
- An upload never completed: after 24 hours. A refused file: its row after 30 days.

Files first, then the row: a storage failure leaves the row for the next run. Photos never
attached to a listing are purged once listings exist (P2-T03).
"""

from datetime import timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import ObjectStorage
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

RETENTION = timedelta(days=30)  # plan P2, T02c
ABANDONED_AFTER = timedelta(hours=24)
BATCH = 200


async def purge_media(
    sessionmaker: async_sessionmaker[AsyncSession], storage: ObjectStorage, *, clock: Clock
) -> int:
    """Returns the number of media removed."""
    now = clock.now()
    removed, failed = 0, set[UUID]()
    while True:
        async with sessionmaker() as db:
            rows = [
                row
                for row in await repository.media_to_purge(
                    db,
                    deleted_before=now - RETENTION,
                    abandoned_before=now - ABANDONED_AFTER,
                    limit=BATCH + len(failed),
                )
                if row.id not in failed
            ]
        if not rows:
            break
        for row in rows:
            try:
                await storage.delete("originals", row.storage_key)
                for variant in row.variants:
                    await storage.delete("variants", variant["key"])
            except Exception:
                logger.exception("media.purge_failed", media_id=str(row.id))
                failed.add(row.id)
                continue
            async with sessionmaker() as db:
                await repository.delete_media_row(db, row.id)
                await commit(db)
            removed += 1
    if removed or failed:
        logger.info("media.purged", removed=removed, failed=len(failed))
    return removed
