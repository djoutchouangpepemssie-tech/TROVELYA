"""GDPR export of the media a member uploaded (registry of ADR-0016). The eraser, which also
deletes the files from storage, arrives with P2-T02c."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.gdpr import register_exporter
from trovelya.modules.media import repository


async def export_media(db: AsyncSession, user_id: UUID) -> dict[str, Any]:
    return {"media": await repository.export_media(db, user_id)}


register_exporter("media", export_media)
