"""SQL of the media module. Only this module's service reads or writes these tables."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
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
