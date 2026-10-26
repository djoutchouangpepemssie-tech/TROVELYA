"""Worker job `process_media` (P2-T02b2, ADR-0019): `processing` → `ready` or `rejected`.

1. The row must still be `processing`. A late or replayed job on a decided media only makes
   sure its original is gone (a deletion that failed after the commit is finished here).
2. The stored size is read again (the presigned length is not trusted alone); the file is
   checked and re-encoded by `images.process_image` in a thread, one image at a time per
   worker.
3. The variants are written under new random keys, then one transaction marks the media
   `ready` and emits `media.ready`. Two runs at once: the one whose update finds the row still
   `processing` wins; the other deletes the variants it wrote.
4. The original is deleted once the outcome is committed: it never outlives processing.

A file refused at any step ends `rejected` with its reason and `media.rejected`.
"""

import asyncio
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
from trovelya.shared.events import emit_event

logger = structlog.get_logger(__name__)

# Plan P2 (T02b): an image this close (dHash bits) to one another member sent first is flagged
# for moderation, never refused. The first sender re-using their own photo is not flagged.
DUPLICATE_DISTANCE = 6
# A 12 Mpx photo takes about 3 s, 49 Mpx about 2.5 s; past this the attempt is retried.
IMAGE_TIMEOUT_S = 60

Session = async_sessionmaker[AsyncSession]


def _signed(value: int) -> int:
    """The unsigned 64-bit dHash as PostgreSQL's signed BIGINT, same bits."""
    return value - (1 << 64) if value >= 1 << 63 else value


async def _status(sessionmaker: Session, media_id: UUID) -> str:
    async with sessionmaker() as db:
        row = await repository.media_to_process(db, media_id)
    return "gone" if row is None else row.status


async def _delete_variants(storage: ObjectStorage, keys: list[str]) -> None:
    for key in keys:
        await storage.delete("variants", key)


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
    if size > max_bytes:
        raise ImageRejectedError("too_large")
    return await storage.get("originals", row.storage_key)


async def _write_variants(
    storage: ObjectStorage, image: ProcessedImage, written: list[str]
) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for variant in image.variants:
        key = new_storage_key()
        written.append(key)
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
    try:
        data = await _read(storage, row, max_bytes)
        async with image_slot or asyncio.Semaphore(1):
            image = await asyncio.wait_for(
                asyncio.to_thread(process_image, data, row.mime_type, max_bytes=max_bytes),
                IMAGE_TIMEOUT_S,
            )
    except ImageRejectedError as rejected:
        return await _reject(sessionmaker, storage, row, rejected.reason)

    written: list[str] = []
    variants = await _write_variants(storage, image, written)
    async with sessionmaker() as db:
        decided = await _mark_ready(db, row, image, variants)
    if not decided:  # another run got there first, or the media was deleted meanwhile
        await _delete_variants(storage, written)
        return await _status(sessionmaker, row.id)
    await storage.delete("originals", row.storage_key)
    logger.info("media.ready", media_id=str(row.id), variants=len(variants))
    return "ready"
