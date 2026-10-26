"""Uploads straight to object storage (P2-T02a3, ADR-0019).

1. `request_upload`: checks the declared type, size and the member's quota, creates the media
   row (`uploading`) under a random key and returns a 5-minute PUT URL that signs the type
   and the length.
2. The browser PUTs the file to storage.
3. `complete_upload` (P2-T02a3b): `uploading` → `processing`, then the worker checks and
   processes the file (P2-T02b). Nothing is served before that.
"""

from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import ObjectStorage, new_storage_key
from trovelya.modules.media.models import IMAGE_TYPES
from trovelya.modules.media.schemas import UploadIn, UploadOut
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

UPLOAD_URL_TTL = timedelta(minutes=5)  # section 13.2: « URL présignées à durée courte »


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
