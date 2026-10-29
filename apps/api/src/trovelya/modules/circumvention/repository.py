"""SQL of the anti-circumvention module (section 7.10)."""

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT = text(
    "INSERT INTO circumvention_detections (id, user_id, source_type, source_id, signals,"
    " matched_spans, confidence, action_taken, review_status, original_sealed, created_at)"
    " VALUES (:id, :user_id, :source_type, :source_id, :signals, CAST(:spans AS jsonb),"
    " :confidence, :action_taken, :review_status, :original_sealed, :created_at)"
)
_EXPORT = text(
    "SELECT id, source_type, source_id, signals, matched_spans, confidence, action_taken,"
    " review_status, created_at FROM circumvention_detections WHERE user_id = :u"
    " ORDER BY created_at, id"
)


async def insert_detection(db: AsyncSession, values: Mapping[str, Any]) -> None:
    await db.execute(_INSERT, {**values, "spans": json.dumps(values["spans"])})


async def export_detections(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    """The member's detections without their sealed original (an export archive must not
    carry a key-bound blob; the listing itself is in the catalog's export)."""
    return [dict(row) for row in (await db.execute(_EXPORT, {"u": user_id})).mappings()]


async def erase_detections(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        text("DELETE FROM circumvention_detections WHERE user_id = :u"), {"u": user_id}
    )
