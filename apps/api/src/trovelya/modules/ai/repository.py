"""SQL of the AI module (hand-written, section 5.4)."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# One member's calls are counted and reserved one at a time (Q45): two at once never pass a
# cap only one of them fits under.
_LOCK_MEMBER = text("SELECT pg_advisory_xact_lock(hashtextextended('ai.assist:' || :u, 0))")
_CALLS_SINCE = text(
    "SELECT created_at FROM ai_listing_suggestions WHERE user_id = :u AND created_at > :since"
    " ORDER BY created_at"
)
_RESERVE = text(
    "INSERT INTO ai_listing_suggestions (id, user_id, media_ids, model, created_at)"
    " VALUES (:id, :u, :media_ids, :model, :now)"
)
_FINISH = text(
    "UPDATE ai_listing_suggestions SET outcome = :outcome, suggestion = CAST(:suggestion AS jsonb),"
    " latency_ms = :latency_ms, cost_microeur = :cost WHERE id = :id AND outcome = 'pending'"
)
_SETTING = text("SELECT value FROM platform_settings WHERE key = :key")


async def setting_int(db: AsyncSession, key: str) -> int:
    """A [PARAM] of `platform_settings`, seeded by the migrations (missing = a bug)."""
    value = await db.scalar(_SETTING, {"key": key})
    if value is None:
        raise LookupError(f"platform setting {key} is missing")
    return int(value)


async def lock_member(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(_LOCK_MEMBER, {"u": str(user_id)})


async def calls_since(db: AsyncSession, user_id: UUID, since: datetime) -> list[datetime]:
    """When the member's calls after `since` were made, oldest first."""
    return list(await db.scalars(_CALLS_SINCE, {"u": user_id, "since": since}))


async def reserve(
    db: AsyncSession,
    *,
    call_id: UUID,
    user_id: UUID,
    media_ids: list[UUID],
    model: str,
    now: datetime,
) -> None:
    params = {"id": call_id, "u": user_id, "media_ids": media_ids, "model": model, "now": now}
    await db.execute(_RESERVE, params)


async def finish(
    db: AsyncSession,
    call_id: UUID,
    *,
    outcome: str,
    suggestion: dict[str, Any],
    latency_ms: int,
    cost_microeur: int | None,
) -> bool:
    """False when the call is not pending (never reserved, or already finished)."""
    params = {"id": call_id, "outcome": outcome, "suggestion": json.dumps(suggestion)}
    result = await db.execute(_FINISH, params | {"latency_ms": latency_ms, "cost": cost_microeur})
    return int(result.rowcount) == 1  # pyright: ignore[reportAttributeAccessIssue, reportUnknownArgumentType, reportUnknownMemberType]


_EXPORT = text(
    "SELECT id, media_ids, model, outcome, suggestion, accepted_fields, latency_ms,"
    " cost_microeur, created_at FROM ai_listing_suggestions WHERE user_id = :u"
    " ORDER BY created_at, id"
)


async def export_calls(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    return [dict(row) for row in (await db.execute(_EXPORT, {"u": user_id})).mappings()]


async def erase_calls(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(text("DELETE FROM ai_listing_suggestions WHERE user_id = :u"), {"u": user_id})


async def delete_calls_before(db: AsyncSession, before: datetime) -> int:
    result = await db.execute(
        text("DELETE FROM ai_listing_suggestions WHERE created_at < :before"), {"before": before}
    )
    return int(result.rowcount)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownArgumentType, reportUnknownMemberType]
