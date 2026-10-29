"""GDPR export and erasure of the catalog (registries of ADR-0016, plan P2 Q13)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.gdpr import register_eraser, register_exporter
from trovelya.modules.catalog import repository


async def export_catalog(db: AsyncSession, user_id: UUID, _: Settings) -> dict[str, Any]:
    return await repository.export_catalog(db, user_id)


register_exporter("catalog", export_catalog)
register_eraser("catalog", repository.erase_catalog)
