"""Domain events through the transactional outbox (section 5.6, ADR-0007).

`emit_event` writes into `outbox_events` in the caller's session: the event exists only if
the business transaction commits. Publishing is done by the worker relay (P0-T06).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
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


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, Any]
    occurred_at: datetime


Handler = Callable[[AsyncSession, OutboxEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Subscription:
    """A handler for one event type; `consumer` is its stable name in `processed_events`."""

    consumer: str
    event_type: str
    handler: Handler


class EventPublisher(Protocol):
    async def publish(self, event: OutboxEvent) -> None: ...


class InMemoryPublisher:
    """Test publisher: keeps every published event in order."""

    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def publish(self, event: OutboxEvent) -> None:
        self.events.append(event)


_MARK_PROCESSED = text(
    "INSERT INTO processed_events (consumer, event_id) VALUES (:consumer, :event_id)"
    " ON CONFLICT DO NOTHING RETURNING event_id"
)


async def consume_once(
    session: AsyncSession,
    consumer: str,
    event_id: UUID,
    handler: Callable[[], Awaitable[None]],
) -> bool:
    """Run `handler` once per (consumer, event), in the caller's transaction.

    Delivery is at least once (section 5.6): the mark and the handler's writes commit together,
    so a rolled-back attempt can be retried and a committed one is never repeated.
    Returns False when the event was already processed by this consumer.
    """
    marked = await session.execute(_MARK_PROCESSED, {"consumer": consumer, "event_id": event_id})
    if marked.scalar_one_or_none() is None:
        return False
    await handler()
    return True
