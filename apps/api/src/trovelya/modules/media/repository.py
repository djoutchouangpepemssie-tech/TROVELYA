"""SQL of the media module. Only this module's service reads or writes these tables."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# What a member gets in the GDPR export: every file they sent, deleted ones included, with
# what is known of it; not the storage keys (internal) nor the image hashes (fraud detection).
_EXPORT_MEDIA = text(
    "SELECT id, kind, purpose, mime_type, bytes, width, height, duration_ms, captured_at,"
    " status, rejection_reason, exif_stripped, moderation,"
    " (SELECT coalesce(jsonb_agg(jsonb_build_object('format', v->'format', 'width', v->'width',"
    " 'height', v->'height')), '[]') FROM jsonb_array_elements(variants) v) AS variants,"
    " created_at, updated_at, deleted_at"
    " FROM media WHERE owner_id = :user_id ORDER BY created_at"
)


async def export_media(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    rows = await db.execute(_EXPORT_MEDIA, {"user_id": user_id})
    return [dict(row) for row in rows.mappings()]
