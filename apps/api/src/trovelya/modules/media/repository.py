"""SQL of the media module. Only this module's service reads or writes these tables."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

# What a member gets in the GDPR export: their files' description, not the storage keys
# (internal) nor the image hashes (fraud detection).
_EXPORT_MEDIA = text(
    "SELECT id, kind, purpose, mime_type, bytes, width, height, status, created_at, deleted_at"
    " FROM media WHERE owner_id = :user_id ORDER BY created_at"
)


async def export_media(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    rows = await db.execute(_EXPORT_MEDIA, {"user_id": user_id})
    return [dict(row) for row in rows.mappings()]


async def setting_int(db: AsyncSession, key: str) -> int:
    """A [PARAM] of `platform_settings`, seeded by the migrations (missing = a bug)."""
    value = await db.scalar(
        text("SELECT value FROM platform_settings WHERE key = :key"), {"key": key}
    )
    if value is None:
        raise LookupError(f"platform setting {key} is missing")
    return int(value)


async def lock_uploads_of(db: AsyncSession, owner_id: UUID) -> None:
    """Serialises one member's upload requests, so two at once cannot both pass the quota."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('media.uploads:' || :owner, 0))"),
        {"owner": str(owner_id)},
    )


async def count_uploads_since(db: AsyncSession, owner_id: UUID, since: datetime) -> int:
    count = await db.scalar(
        text("SELECT count(*) FROM media WHERE owner_id = :owner AND created_at > :since"),
        {"owner": owner_id, "since": since},
    )
    return int(count or 0)


async def insert_upload(
    db: AsyncSession,
    *,
    media_id: UUID,
    owner_id: UUID,
    purpose: str,
    storage_key: str,
    mime_type: str,
    size: int,
    now: datetime,
) -> None:
    await db.execute(
        text(
            "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
            " status, created_at, updated_at)"
            " VALUES (:id, :owner, 'image', :purpose, :key, :mime, :size, 'uploading', :now, :now)"
        ),
        {
            "id": media_id,
            "owner": owner_id,
            "purpose": purpose,
            "key": storage_key,
            "mime": mime_type,
            "size": size,
            "now": now,
        },
    )


async def start_processing(db: AsyncSession, media_id: UUID, owner_id: UUID) -> str | None:
    """`uploading` → `processing` for the owner's media. Returns "started", or the status found
    when it was not `uploading`, or None when the media is not theirs or does not exist."""
    started = await db.scalar(
        text(
            "UPDATE media SET status = 'processing' WHERE id = :id AND owner_id = :owner"
            " AND status = 'uploading' AND deleted_at IS NULL RETURNING id"
        ),
        {"id": media_id, "owner": owner_id},
    )
    if started is not None:
        return "started"
    return await db.scalar(
        text(
            "SELECT status FROM media WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
        ),
        {"id": media_id, "owner": owner_id},
    )


async def owned_media(db: AsyncSession, media_id: UUID, owner_id: UUID) -> Row[Any] | None:
    return (
        await db.execute(
            text(
                "SELECT id, purpose, mime_type, status, width, height, variants, rejection_reason"
                " FROM media WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
            ),
            {"id": media_id, "owner": owner_id},
        )
    ).one_or_none()
