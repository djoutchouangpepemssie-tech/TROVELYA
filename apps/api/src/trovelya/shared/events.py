"""Domain events through the transactional outbox (section 5.6, ADR-0007).

`emit_event` writes into `outbox_events` in the caller's session: the event exists only if
the business transaction commits. Publishing is done by the worker relay (P0-T06).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.shared.ids import new_id

_INSERT = text(
    "INSERT INTO outbox_events (id, type, aggregate_type, aggregate_id, payload)"
    " VALUES (:id, :type, :aggregate_type, :aggregate_id, :payload)"
).bindparams(bindparam("payload", type_=JSONB))


async def emit_event(
    session: AsyncSession,
    *,
    type: str,  # noqa: A002 — the column and the spec call it "type"
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
    version: int = 1,
) -> UUID:
    if "v" in payload:
        raise ValueError("payload key 'v' is reserved for the schema version")
    event_id = new_id()
    await session.execute(
        _INSERT,
        {
            "id": event_id,
            "type": type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "payload": {**payload, "v": version},
        },
    )
    return event_id
