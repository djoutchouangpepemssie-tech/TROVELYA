"""Worker job `process_media` (P2-T02b2, ADR-0019): `processing` → `ready` or `rejected`.

1. The row must still be `processing` (a replayed or late job changes nothing).
2. The stored size is read again (the presigned length is not trusted alone), then the file
   is checked and re-encoded by `images.process_image`, in a thread.
3. The variants are written under new random keys, then one transaction marks the media
   `ready` and emits `media.ready`. Two runs at once: the one whose update finds the row still
   `processing` wins; the other deletes the variants it wrote.
4. The original is deleted once the outcome is committed: it never outlives processing.

A file refused at any step ends `rejected` with its reason and `media.rejected`.
"""

import asyncio
import threading
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
# A 12 Mpx photo takes about 3 s (8 variants); the worker gives up after this and retries.
PROCESS_TIMEOUT_S = 120
# One image decoded at a time per worker process: a 50 Mpx image takes about 200 MB in RGBA.
# A thread lock, taken inside the thread, so it belongs to no event loop.
_ONE_IMAGE_AT_A_TIME = threading.Lock()


def _process_one(data: bytes, mime_type: str, max_bytes: int) -> ProcessedImage:
    with _ONE_IMAGE_AT_A_TIME:
        return process_image(data, mime_type, max_bytes=max_bytes)


def _signed(value: int) -> int:
    """The unsigned 64-bit dHash as PostgreSQL's signed BIGINT, same bits."""
    return value - (1 << 64) if value >= 1 << 63 else value


async def _status(sessionmaker: async_sessionmaker[AsyncSession], media_id: UUID) -> str:
    async with sessionmaker() as db:
        row = await repository.media_to_process(db, media_id)
    return "gone" if row is None else row.status


async def _reject(
    sessionmaker: async_sessionmaker[AsyncSession],
    storage: ObjectStorage,
    row: Any,
    reason: str,
) -> str:
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


async def process_media(
    sessionmaker: async_sessionmaker[AsyncSession], storage: ObjectStorage, media_id: UUID
) -> str:
    """Returns the media's status afterwards, or "gone" when it does not exist or was deleted."""
    async with sessionmaker() as db:
        row = await repository.media_to_process(db, media_id)
        if row is None or row.status != "processing":
            return "gone" if row is None else row.status
        max_bytes = await repository.setting_int(db, "media.max_image_bytes")
    try:
        size = await storage.size("originals", row.storage_key)
        if size is None:
            raise ImageRejectedError("missing_file")
        if size > max_bytes:
            raise ImageRejectedError("too_large")
        data = await storage.get("originals", row.storage_key)
        image = await asyncio.to_thread(_process_one, data, row.mime_type, max_bytes)
    except ImageRejectedError as rejected:
        return await _reject(sessionmaker, storage, row, rejected.reason)

    variants: list[dict[str, Any]] = []
    for variant in image.variants:
        key = new_storage_key()
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
    perceptual_hash = _signed(image.dhash)
    async with sessionmaker() as db:
        first = await repository.oldest_similar_media(db, perceptual_hash, DUPLICATE_DISTANCE)
        duplicate = first.id if first is not None and first.owner_id != row.owner_id else None
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
    if not decided:  # another run got there first: keep its variants, not ours
        for variant in variants:
            await storage.delete("variants", variant["key"])
        return await _status(sessionmaker, row.id)
    await storage.delete("originals", row.storage_key)
    logger.info("media.ready", media_id=str(row.id), variants=len(variants))
    return "ready"
