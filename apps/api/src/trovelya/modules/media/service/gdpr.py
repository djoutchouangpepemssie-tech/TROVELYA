"""GDPR export and erasure of the media a member uploaded (registries of ADR-0016).

The eraser runs inside the account's erasure transaction: it hides every photo and clears
what they say of the person; the daily purge (purge.py) then deletes the files from storage
and the rows, without waiting for the usual retention.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.gdpr import register_eraser, register_exporter
from trovelya.modules.media import repository


async def export_media(db: AsyncSession, user_id: UUID) -> dict[str, Any]:
    return {"media": await repository.export_media(db, user_id)}


register_exporter("media", export_media)
register_eraser("media", repository.erase_media)
