"""Public service of the AI module (P2-T06a): the only entry point for other modules.

The calls to the provider (reserved, counted over 24 rolling hours, Q45) arrive with
P2-T06a1b; this part keeps the log's GDPR duties (Q46)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.gdpr import register_eraser, register_exporter
from trovelya.modules.ai import repository
from trovelya.modules.ai.adapters.provider import AIProvider, ImageRef, Leaf
from trovelya.modules.ai.schemas import ListingSuggestion

__all__ = ["AIProvider", "ImageRef", "Leaf", "ListingSuggestion", "unavailable"]


def unavailable() -> AppError:
    return AppError(ErrorCode.AI_UNAVAILABLE, 503)


async def _export(db: AsyncSession, user_id: UUID, settings: Settings) -> dict[str, Any]:
    """Q46: every call of the member, with what the AI said (right of access)."""
    return {"ai_listing_suggestions": await repository.export_calls(db, user_id)}


register_exporter("ai", _export)
register_eraser("ai", repository.erase_calls)  # Q46: gone with the account
