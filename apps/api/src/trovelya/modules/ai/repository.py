"""SQL of the AI module (hand-written, section 5.4)."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_EXPORT = text(
    "SELECT id, media_ids, model, outcome, suggestion, accepted_fields, latency_ms,"
    " cost_microeur, created_at FROM ai_listing_suggestions WHERE user_id = :u"
    " ORDER BY created_at, id"
)


async def export_calls(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    return [dict(row) for row in (await db.execute(_EXPORT, {"u": user_id})).mappings()]


async def erase_calls(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(text("DELETE FROM ai_listing_suggestions WHERE user_id = :u"), {"u": user_id})
