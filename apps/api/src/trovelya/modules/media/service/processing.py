"""Worker job `process_media` (P2-T02b2, ADR-0019): `processing` → `ready` or `rejected`.

1. The row must still be `processing`. A late or replayed job on a decided media only makes
   sure its original is gone (a deletion that failed after the commit is finished here).
2. The stored size is read again (the presigned length is not trusted alone) and at most
   max_bytes + 1 bytes are read; the file is checked and re-encoded by `images.process_image`
   in a thread, one image at a time per worker.
3. The variants are written under new random keys, then one transaction marks the media
   `ready` and emits `media.ready`. Two runs at once: the one whose update finds the row still
   `processing` wins; the other deletes the variants it wrote. Any failure after a variant was
   written deletes them too: nothing public is left unreferenced.
4. The original is deleted once the outcome is committed: it never outlives processing.

A file refused at any step ends `rejected` with its reason and `media.rejected`. A media whose
job keeps failing (tasks.py) or died (`recover_stuck_media`) ends `rejected` with
`processing_failed`: never `processing` for ever.
"""

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import ObjectStorage, new_storage_key
from trovelya.modules.media.service.images import (
    ImageRejectedError,
    ProcessedImage,
    process_image,
)
from trovelya.modules.media.service.uploads import PROCESS_JOB
from trovelya.shared.clock import Clock
from trovelya.shared.events import emit_event

logger = structlog.get_logger(__name__)

# Plan P2 (T02b): an image this close (dHash bits) to one another member sent first is flagged
# for moderation, never refused. The first sender re-using their own photo is not flagged.
DUPLICATE_DISTANCE = 6
# A 12 Mpx photo takes about 3 s, 49 Mpx about 2.5 s; past this the attempt is retried.
IMAGE_TIMEOUT_S = 60
# No attempt started for this long (three tries and their delays take under 10 minutes): the
# job was lost (worker stopped or killed). It is enqueued again; after GIVE_UP the media is
# rejected, so a photo never stays `processing` for ever.
STUCK_AFTER = timedelta(minutes=15)
GIVE_UP = timedelta(hours=24)
PROCESSING_FAILED = "processing_failed"

Session = async_sessionmaker[AsyncSession]


def _signed(value: int) -> int:
    """The unsigned 64-bit dHash as PostgreSQL's signed BIGINT, same bits."""
    return value - (1 << 64) if value >= 1 << 63 else value


async def _status(sessionmaker: Session, media_id: UUID) -> str:
    async with sessionmaker() as db:
        row = await repository.media_to_process(db, media_id)
    return "gone" if row is None else row.status


async def _delete_variants(storage: ObjectStorage, keys: list[str]) -> None:
    """Best effort while another error may be on its way: each key is tried."""
    for key in keys:
        try:
            await storage.delete("variants", key)
        except Exception:
            logger.exception("media.variant_cleanup_failed")


async def _reject(sessionmaker: Session, storage: ObjectStorage, row: Any, reason: str) -> str:
    async with sessionmaker() as db:
        decided = await repository.mark_rejected(db, row.id, reason)
        if decided:
            await emit_event(
                db,
                type="media.rejected",
                aggregate_type="media",
                aggregate_id=row.id,
                payload={"media_id": str(row.id), "reason": reason},
            )
            await commit(db)
    if not decided:
        return await _status(sessionmaker, row.id)
    await storage.delete("originals", row.storage_key)
    logger.info("media.rejected", media_id=str(row.id), reason=reason)
    return "rejected"


async def _read(storage: ObjectStorage, row: Any, max_bytes: int) -> bytes:
    size = await storage.size("originals", row.storage_key)
    if size is None:
        raise ImageRejectedError("missing_file")
    data = await storage.get("originals", row.storage_key, max_bytes=max_bytes)
    if max(size, len(data)) > max_bytes:  # the size read first, or what came back
        raise ImageRejectedError("too_large")
    return data


async def _write_variants(
    storage: ObjectStorage, image: ProcessedImage, written: list[str]
) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for variant in image.variants:
        key = new_storage_key()
        written.append(key)  # before the upload: a failed upload may still leave the object
        await storage.put("variants", key, variant.data, content_type=f"image/{variant.format}")
        variants.append(
            {
                "format": variant.format,
                "width": variant.width,
                "height": variant.height,
                "key": key,
                "bytes": len(variant.data),
            }
        )
    return variants


async def _mark_ready(
    db: AsyncSession, row: Any, image: ProcessedImage, variants: list[dict[str, Any]]
) -> bool:
    perceptual_hash = _signed(image.dhash)
    duplicate = None
    if row.purpose == "listing":
        first = await repository.oldest_similar_media(db, perceptual_hash, DUPLICATE_DISTANCE)
        if first is not None and first.owner_id != row.owner_id:
            duplicate = first.id
    decided = await repository.mark_ready(
        db,
        row.id,
        width=image.width,
        height=image.height,
        sha256=image.sha256,
        perceptual_hash=perceptual_hash,
        variants=variants,
        moderation={"duplicate_of": str(duplicate)} if duplicate else {},
    )
    if decided:
        await emit_event(
            db,
            type="media.ready",
            aggregate_type="media",
            aggregate_id=row.id,
            payload={"media_id": str(row.id), "owner_id": str(row.owner_id)},
        )
        await commit(db)
    return decided


async def _decode(
    slot: asyncio.Semaphore, data: bytes, mime_type: str, max_bytes: int
) -> ProcessedImage:
    """`process_image` in a thread, within IMAGE_TIMEOUT_S. A thread cannot be stopped: when the
    wait gives up, the slot stays taken until the thread really ends, so a slow hostile file
    never runs next to another decoding."""
    await slot.acquire()
    task = asyncio.ensure_future(
        asyncio.to_thread(process_image, data, mime_type, max_bytes=max_bytes)
    )

    def release(done: asyncio.Future[ProcessedImage]) -> None:
        slot.release()
        if not done.cancelled():
            done.exception()  # an abandoned attempt's error is retrieved, not reported twice

    task.add_done_callback(release)
    return await asyncio.wait_for(asyncio.shield(task), IMAGE_TIMEOUT_S)


async def process_media(
    sessionmaker: Session,
    storage: ObjectStorage,
    media_id: UUID,
    *,
    image_slot: asyncio.Semaphore | None = None,
) -> str:
    """Returns the media's status afterwards, or "gone" when it does not exist or was deleted.
    `image_slot` limits the images decoded at once (the worker shares one; one by default)."""
    async with sessionmaker() as db:
        row = await repository.media_to_process(db, media_id)
        if row is None:
            return "gone"
        if row.status != "processing":
            if row.status in {"ready", "rejected"}:
                await storage.delete("originals", row.storage_key)
            return row.status
        max_bytes = await repository.setting_int(db, "media.max_image_bytes")
        await repository.mark_attempt(db, row.id)  # the recovery cron leaves it alone
        await commit(db)
    try:
        data = await _read(storage, row, max_bytes)
        image = await _decode(image_slot or asyncio.Semaphore(1), data, row.mime_type, max_bytes)
    except ImageRejectedError as rejected:
        return await _reject(sessionmaker, storage, row, rejected.reason)

    written: list[str] = []
    try:
        variants = await _write_variants(storage, image, written)
        async with sessionmaker() as db:
            decided = await _mark_ready(db, row, image, variants)
    except BaseException:
        await _delete_variants(storage, written)
        raise
    if not decided:  # another run got there first, or the media was deleted meanwhile
        await _delete_variants(storage, written)
        return await _status(sessionmaker, row.id)
    await storage.delete("originals", row.storage_key)
    logger.info("media.ready", media_id=str(row.id), variants=len(variants))
    return "ready"


async def fail_media(sessionmaker: Session, storage: ObjectStorage, media_id: UUID) -> str:
    """Gives up on a media still `processing`: `rejected` with `processing_failed`."""
    async with sessionmaker() as db:
        row = await repository.media_to_process(db, media_id)
    if row is None:
        return "gone"
    if row.status != "processing":
        if row.status in {"ready", "rejected"}:  # its deletion may have failed every time
            await storage.delete("originals", row.storage_key)
        return row.status
    return await _reject(sessionmaker, storage, row, PROCESSING_FAILED)


async def recover_stuck_media(
    sessionmaker: Session, storage: ObjectStorage, queue: Any, *, clock: Clock
) -> int:
    """Cron: a media with no attempt for STUCK_AFTER lost its job; it is enqueued again (one
    recovery job per media at a time), and rejected once GIVE_UP has passed since its upload."""
    now = clock.now()
    async with sessionmaker() as db:
        stuck = await repository.stuck_in_processing(db, now - STUCK_AFTER)
    for media_id, created_at in stuck:
        if created_at < now - GIVE_UP:
            await fail_media(sessionmaker, storage, media_id)
        else:
            await queue.enqueue_job(
                PROCESS_JOB, str(media_id), _job_id=f"media-recovery:{media_id}"
            )
    if stuck:
        logger.warning("media.stuck_recovered", count=len(stuck))
    return len(stuck)
