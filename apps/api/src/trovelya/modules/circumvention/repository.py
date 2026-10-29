"""SQL of the anti-circumvention module (section 7.10)."""

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# The same passages of the same source found again (a listing put back online) are one
# detection, not a new case for the review or the sanctions.
_INSERT = text(
    "INSERT INTO circumvention_detections (id, user_id, source_type, source_id, signals,"
    " matched_spans, confidence, action_taken, review_status, original_sealed, created_at)"
    " SELECT :id, :user_id, :source_type, :source_id, :signals, CAST(:spans AS jsonb),"
    " :confidence, :action_taken, :review_status, :original_sealed, :created_at"
    " WHERE NOT EXISTS (SELECT 1 FROM circumvention_detections WHERE user_id = :user_id"
    " AND source_type = :source_type AND source_id = :source_id"
    " AND action_taken = :action_taken AND matched_spans = CAST(:spans AS jsonb))"
)
_EXPORT = text(
    "SELECT id, source_type, source_id, signals, matched_spans, confidence, action_taken,"
    " review_status, created_at, original_sealed FROM circumvention_detections"
    " WHERE user_id = :u ORDER BY created_at, id"
)
# Q36: what was reviewed or confirmed goes after the retention, counted from the review (a
# late review keeps its evidence 180 days); a detection awaiting its review stays.
_DELETE_OLD = text(
    "DELETE FROM circumvention_detections WHERE COALESCE(reviewed_at, created_at) < :before"
    " AND review_status <> 'pending'"
)


async def insert_detection(db: AsyncSession, values: Mapping[str, Any]) -> None:
    await db.execute(_INSERT, {**values, "spans": json.dumps(values["spans"])})


async def export_detections(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    """The member's detections, the sealed original included (the service opens it)."""
    return [dict(row) for row in (await db.execute(_EXPORT, {"u": user_id})).mappings()]


async def erase_detections(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        text("DELETE FROM circumvention_detections WHERE user_id = :u"), {"u": user_id}
    )


async def delete_detections_before(db: AsyncSession, before: datetime) -> int:
    result = await db.execute(_DELETE_OLD, {"before": before})
    return int(result.rowcount)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownArgumentType, reportUnknownMemberType]


async def setting_int(db: AsyncSession, key: str) -> int:
    """A [PARAM] of `platform_settings`, seeded by the migrations (missing = a bug)."""
    value = await db.scalar(
        text("SELECT value FROM platform_settings WHERE key = :key"), {"key": key}
    )
    if value is None:
        raise LookupError(f"platform setting {key} is missing")
    return int(value)


async def detections_of(
    db: AsyncSession, source_type: str, source_ids: list[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    """What was found in each source, never the original: signals, action, part, review."""
    rows = await db.execute(
        text(
            "SELECT source_id, signals, action_taken, review_status,"
            " matched_spans -> 0 ->> 'part' AS part FROM circumvention_detections"
            " WHERE source_type = :t AND source_id = ANY(:s) ORDER BY created_at, id"
        ),
        {"t": source_type, "s": source_ids},
    )
    found: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows.mappings():
        detection = dict(row)
        found.setdefault(detection.pop("source_id"), []).append(detection)
    return found
