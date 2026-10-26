"""Purge of media files and rows, every hour (P2-T02c2, ADR-0019, PII.md).

1. Marked deleted: uploads never completed and avatar photos never chosen after 24 hours,
   refusals after `retention.deleted_media_days` (30). Marked first and committed, so a worker
   finishing late (`mark_ready` needs a media not deleted) or a member choosing the photo as
   their avatar (`check_avatar`) cannot race with the deletion of its files.
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
# An erased account's files still stored after this are reported (the erasure is recorded as
# completed when the database is anonymised; its files follow within the hour).
ERASED_FILES_ALERT_AFTER = timedelta(hours=48)
BATCH = 200
# Storage down: the run stops rather than failing on every row until its timeout.
MAX_CONSECUTIVE_FAILURES = 20

Session = async_sessionmaker[AsyncSession]


async def _delete_files(sessionmaker: Session, storage: ObjectStorage, *, clock: Clock) -> int:
    deleted, consecutive_failures, after = 0, 0, None
    while consecutive_failures < MAX_CONSECUTIVE_FAILURES:
        async with sessionmaker() as db:
            rows = await repository.files_to_delete(db, after=after, limit=BATCH)
        if not rows:
            break
        for row in rows:
            after = row.id
            try:
                await storage.delete("originals", row.storage_key)
                for variant in row.variants:
                    await storage.delete("variants", variant["key"])
            except Exception:
                logger.exception("media.purge_failed", media_id=str(row.id))
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                continue
            consecutive_failures = 0
            async with sessionmaker() as db:
                await repository.mark_files_deleted(db, row.id, clock.now())
                await commit(db)
            deleted += 1
    return deleted


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
        pending = await repository.erased_files_pending(
            db, erased_before=now - ERASED_FILES_ALERT_AFTER
        )
        await commit(db)
    if pending:
        logger.error("media.erased_files_pending", count=pending)
    if marked or files or rows:
        logger.info("media.purged", marked=marked, files=files, rows=rows)
    return files
