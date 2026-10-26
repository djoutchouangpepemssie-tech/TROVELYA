"""Purge of media files and rows, every hour (P2-T02c2, ADR-0019, PII.md).

1. Marked deleted: uploads never completed and avatar photos never chosen after 24 hours,
   refusals after `retention.deleted_media_days` (30). Marked first and committed, so a worker
   finishing late (`mark_ready` needs a media not deleted) cannot race with the deletion of
   its files.
2. Files of every deleted media: original and variants leave storage at the next run, an
   hour at most after the photo was withdrawn or the account erased (ADR-0019: a withdrawn
   photo's public URL must stop working). A storage failure leaves them for the next run.
3. Rows whose files are gone: after the retention, at once for an erased account or a media
   that never became a photo.

Photos never attached to a listing are purged once listings exist (P2-T03).
"""

from datetime import timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import ObjectStorage
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

ABANDONED_AFTER = timedelta(hours=24)  # plan P2, T02c
BATCH = 200

Session = async_sessionmaker[AsyncSession]


async def _delete_files(sessionmaker: Session, storage: ObjectStorage, *, clock: Clock) -> int:
    deleted, after = 0, None
    while True:
        async with sessionmaker() as db:
            rows = await repository.files_to_delete(db, after=after, limit=BATCH)
        if not rows:
            return deleted
        for row in rows:
            after = row.id
            try:
                await storage.delete("originals", row.storage_key)
                for variant in row.variants:
                    await storage.delete("variants", variant["key"])
            except Exception:
                logger.exception("media.purge_failed", media_id=str(row.id))
                continue
            async with sessionmaker() as db:
                await repository.mark_files_deleted(db, row.id, clock.now())
                await commit(db)
            deleted += 1


async def purge_media(sessionmaker: Session, storage: ObjectStorage, *, clock: Clock) -> int:
    """Returns the number of media whose files were deleted."""
    now = clock.now()
    async with sessionmaker() as db:
        retention = timedelta(days=await repository.setting_int(db, "retention.deleted_media_days"))
        marked = await repository.mark_for_purge(
            db, now=now, abandoned_before=now - ABANDONED_AFTER, refused_before=now - retention
        )
        await commit(db)
    files = await _delete_files(sessionmaker, storage, clock=clock)
    async with sessionmaker() as db:
        rows = await repository.delete_purged_rows(db, deleted_before=now - retention)
        await commit(db)
    if marked or files or rows:
        logger.info("media.purged", marked=marked, files=files, rows=rows)
    return files
