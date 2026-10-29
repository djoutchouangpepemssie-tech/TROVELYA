"""Purge of media files and rows, every hour (P2-T02c2, ADR-0019, PII.md).

1. Marked deleted: uploads never completed, avatar photos never chosen and listing photos in
   no listing after 24 hours, refusals after `retention.deleted_media_days` (30). Marked first
   and committed, so a worker finishing late (`mark_ready` needs a media not deleted) cannot
   race with the deletion of its files; a photo a member is choosing as their avatar or
   attaching to a listing is skipped (`mark_for_purge`).
1b. Quarantined photos (plan Q40): their variants move from the public bucket to a private
   copy (same keys, `originals` bucket), kept for the appeal; deleted with the photo.
2. Files of every deleted media: original and variants leave storage at the next run, an
   hour at most after the photo was withdrawn or the account erased (ADR-0019: a withdrawn
   photo's public URL must stop working). A failure is recorded on the row; the media is
   retried at the next run, after the ones that never failed. Files still stored 48 hours
   after the deletion are reported.
3. Rows whose files are gone: after the retention, at once for an erased account or a media
   that never became a photo.
"""

from datetime import datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import ObjectStorage
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

ABANDONED_AFTER = timedelta(hours=24)  # plan P2, T02c
# Files of a deleted media still stored after this are reported (an erasure is recorded as
# completed when the database is anonymised; its files follow within the hour).
FILES_OVERDUE_AFTER = timedelta(hours=48)
BATCH = 200
# Storage down: the run stops rather than failing on every row until its timeout (at least 1).
MAX_CONSECUTIVE_FAILURES = 20

Session = async_sessionmaker[AsyncSession]


class _Run:
    def __init__(self, started: datetime) -> None:
        self.started = started  # failures from this run are retried at the next one
        self.deleted = 0
        self.consecutive_failures = 0

    @property
    def stopped(self) -> bool:
        return self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES


async def _delete_files(
    sessionmaker: Session, storage: ObjectStorage, run: _Run, *, clock: Clock, retry: bool
) -> None:
    """One pass: the media that never failed, or (`retry`) the ones that failed before."""
    after = None
    while not run.stopped:
        async with sessionmaker() as db:
            rows = await repository.files_to_delete(
                db, retry_failed_before=run.started if retry else None, after=after, limit=BATCH
            )
        if not rows:
            return
        for row in rows:
            after = row.id
            try:
                await storage.delete("originals", row.storage_key)
                for variant in row.variants:
                    await storage.delete("variants", variant["key"])
                    if row.quarantine_moved_at is not None:  # its private copy (Q40)
                        await storage.delete("originals", variant["key"])
            except Exception:
                logger.exception("media.purge_failed", media_id=str(row.id))
                async with sessionmaker() as db:
                    await repository.mark_files_purge_failed(db, row.id, clock.now())
                    await commit(db)
                run.consecutive_failures += 1
                if run.stopped:
                    logger.error("media.purge_stopped", failures=run.consecutive_failures)
                    return
                continue
            run.consecutive_failures = 0
            async with sessionmaker() as db:
                await repository.mark_files_deleted(db, row.id, clock.now())
                await commit(db)
            run.deleted += 1


async def _move_quarantined(sessionmaker: Session, storage: ObjectStorage, *, clock: Clock) -> None:
    """Q40: a quarantined photo's variants leave the public bucket for a private copy (copied
    before deleted: never lost; a variant already gone has nothing to move). A failure leaves
    the photo for the next run; failures in a row stop this step, not the purge."""
    async with sessionmaker() as db:
        rows = await repository.quarantined_to_move(db, limit=BATCH)
    failures = 0
    for row in rows:
        try:
            for variant in row.variants:
                if await storage.size("variants", variant["key"]) is None:
                    continue
                data = await storage.get("variants", variant["key"])
                await storage.put("originals", variant["key"], data, content_type="image/webp")
                await storage.delete("variants", variant["key"])
        except Exception:
            logger.exception("media.quarantine_failed", media_id=str(row.id))
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                return
            continue
        failures = 0
        async with sessionmaker() as db:
            await repository.mark_quarantine_moved(db, row.id, clock.now())
            await commit(db)


async def purge_media(sessionmaker: Session, storage: ObjectStorage, *, clock: Clock) -> int:
    """Returns the number of media whose files were deleted."""
    now = clock.now()
    async with sessionmaker() as db:
        retention = timedelta(days=await repository.setting_int(db, "retention.deleted_media_days"))
        marked = await repository.mark_for_purge(
            db, now=now, abandoned_before=now - ABANDONED_AFTER, refused_before=now - retention
        )
        await commit(db)
    run = _Run(now)
    await _move_quarantined(sessionmaker, storage, clock=clock)
    await _delete_files(sessionmaker, storage, run, clock=clock, retry=False)
    await _delete_files(sessionmaker, storage, run, clock=clock, retry=True)
    files = run.deleted
    async with sessionmaker() as db:
        rows = await repository.delete_purged_rows(db, deleted_before=now - retention)
        overdue = await repository.files_overdue(db, deleted_before=now - FILES_OVERDUE_AFTER)
        await commit(db)
    if overdue:
        logger.error("media.files_overdue", count=overdue)
    if marked or files or rows:
        logger.info("media.purged", marked=marked, files=files, rows=rows)
    return files
