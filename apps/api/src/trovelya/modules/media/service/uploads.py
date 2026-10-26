"""Uploads straight to object storage (P2-T02a3, ADR-0019).

1. `request_upload`: checks the declared type, size and the member's quota, creates the media
   row (`uploading`) under a random key and returns a 5-minute PUT URL that signs the type
   and the length.
2. The browser PUTs the file to storage.
3. `complete_upload`: `uploading` → `processing`, then the worker checks and processes the
   file (P2-T02b). Nothing is served before that.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.db import on_commit
from trovelya.core.email import JobQueue
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import ObjectStorage, new_storage_key
from trovelya.modules.media.models import IMAGE_TYPES
from trovelya.modules.media.schemas import MediaOut, UploadIn, UploadOut, VariantOut
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

UPLOAD_URL_TTL = timedelta(minutes=5)  # section 13.2: « URL présignées à durée courte »
PROCESS_JOB = "process_media"


async def request_upload(
    db: AsyncSession,
    *,
    owner_id: UUID,
    body: UploadIn,
    storage: ObjectStorage,
    clock: Clock,
) -> UploadOut:
    if body.mime_type not in IMAGE_TYPES:
        raise AppError(ErrorCode.MEDIA_TYPE_REJECTED, 422)
    if body.bytes > await repository.setting_int(db, "media.max_image_bytes"):
        raise AppError(ErrorCode.MEDIA_TOO_LARGE, 413)
    now = clock.now()
    await repository.lock_uploads_of(db, owner_id)
    for window, key in ((timedelta(hours=1), "hour"), (timedelta(days=1), "day")):
        limit = await repository.setting_int(db, f"media.uploads_per_{key}")
        if await repository.count_uploads_since(db, owner_id, now - window) >= limit:
            raise AppError(ErrorCode.UPLOAD_LIMIT, 429)
    media_id, storage_key = new_id(), new_storage_key()
    await repository.insert_upload(
        db,
        media_id=media_id,
        owner_id=owner_id,
        purpose=body.purpose,
        storage_key=storage_key,
        mime_type=body.mime_type,
        size=body.bytes,
        now=now,
    )
    upload = storage.presign_put(
        "originals",
        storage_key,
        content_type=body.mime_type,
        content_length=body.bytes,
        expires_in=int(UPLOAD_URL_TTL.total_seconds()),
    )
    return UploadOut(
        media_id=media_id,
        upload_url=upload.url,
        headers=upload.headers,
        expires_at=now + UPLOAD_URL_TTL,
    )


async def complete_upload(
    db: AsyncSession, *, owner_id: UUID, media_id: UUID, queue: JobQueue
) -> None:
    """The worker is asked after commit (it must find the row `processing`). Calling again
    while the media is still `processing` asks again: the client retries when the first
    answer was lost or the queue failed after commit, and `process_media` is idempotent
    (P2-T02b). Once the worker has decided (ready or rejected), 409."""
    outcome = await repository.start_processing(db, media_id, owner_id)
    if outcome is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if outcome not in {"started", "processing"}:
        raise AppError(ErrorCode.MEDIA_ALREADY_COMPLETED, 409)

    async def push() -> None:
        await queue.enqueue_job(PROCESS_JOB, str(media_id))

    on_commit(db, push)


def _variants(rows: list[dict[str, Any]], public_url: str | None) -> list[VariantOut]:
    base = (public_url or "").rstrip("/")
    return [
        VariantOut(
            format=v["format"], width=v["width"], height=v["height"], url=f"{base}/{v['key']}"
        )
        for v in rows
    ]


async def get_media(
    db: AsyncSession, *, owner_id: UUID, media_id: UUID, public_url: str | None
) -> MediaOut:
    row = await repository.owned_media(db, media_id, owner_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return MediaOut(
        id=row.id,
        purpose=row.purpose,
        mime_type=row.mime_type,
        status=row.status,
        width=row.width,
        height=row.height,
        variants=_variants(row.variants, public_url) if row.status == "ready" else [],
        rejection_reason=row.rejection_reason,
    )
