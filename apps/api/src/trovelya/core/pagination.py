"""Cursor pagination (section 11.3): `?limit=24&cursor=<opaque>` → `{data, next_cursor,
has_more}`, `limit` at most 100. A cursor is the sort key of the last item served, encoded."""

import base64
import json
from datetime import datetime
from typing import Annotated
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


def decode_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    """None for the first page; 422 for a cursor this API did not make."""
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        at, item_id = json.loads(raw)
        return datetime.fromisoformat(at), UUID(item_id)
    except (ValueError, TypeError) as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            422,
            errors=[FieldError(field="cursor", code="invalid", message="Curseur invalide")],
        ) from exc
