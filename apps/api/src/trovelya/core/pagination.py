"""Cursor pagination (section 11.3): `?limit=24&cursor=<opaque>` → `{data, next_cursor,
has_more}`, `limit` at most 100. A cursor is the sort key of the last item served, encoded."""

import base64
import json
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import Query

from trovelya.core.errors import AppError, ErrorCode, FieldError

DEFAULT_LIMIT = 24
MAX_LIMIT = 100

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Cursor = Annotated[str | None, Query(max_length=200)]


def encode_cursor(at: datetime, item_id: UUID) -> str:
    raw = json.dumps([at.isoformat(), str(item_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# Cursors carry dates of this platform only: anything outside is forged.
EARLIEST = datetime(2000, 1, 1, tzinfo=UTC)
LATEST = datetime(2100, 1, 1, tzinfo=UTC)


def _invalid() -> AppError:
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        422,
        errors=[FieldError(field="cursor", code="invalid", message="Curseur invalide")],
    )


def decode_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    """None for the first page; 422 for any cursor this API did not make (wrong types, a date
    without time zone or out of range: never a 500)."""
    if cursor is None:
        return None
    try:
        decoded: object = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except ValueError as exc:
        raise _invalid() from exc
    parts = cast(list[object], decoded) if isinstance(decoded, list) else []
    if len(parts) != 2 or not all(isinstance(part, str) for part in parts):
        raise _invalid()
    at_text, id_text = str(parts[0]), str(parts[1])
    try:
        at, item_id = datetime.fromisoformat(at_text), UUID(id_text)
        if at.tzinfo is None or not EARLIEST <= at.astimezone(UTC) < LATEST:
            raise _invalid()
    except (ValueError, OverflowError) as exc:
        raise _invalid() from exc
    return at, item_id
