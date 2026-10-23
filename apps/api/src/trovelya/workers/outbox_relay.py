"""Outbox relay: publishes committed domain events, in id order, at least once (ADR-0007)."""

import json

import structlog
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.shared.clock import Clock
from trovelya.shared.events import EventPublisher, OutboxEvent

logger = structlog.get_logger(__name__)

EVENTS_STREAM = "trv:events"
STREAM_MAX_LENGTH = 100_000

# SKIP LOCKED: two relays never take the same rows; each publishes its own batch in id order.
_CLAIM = text(
    "SELECT id, type, aggregate_type, aggregate_id, payload, occurred_at FROM outbox_events"
    " WHERE published_at IS NULL ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED"
)
_MARK = text("UPDATE outbox_events SET published_at = :now WHERE id = ANY(:ids)")


class RedisStreamPublisher:
    def __init__(self, redis: Redis, stream: str = EVENTS_STREAM) -> None:
        self._redis = redis
        self._stream = stream

    async def publish(self, event: OutboxEvent) -> None:
        await self._redis.xadd(  # pyright: ignore[reportUnknownMemberType]
            self._stream,
            {
                "id": str(event.id),
                "type": event.type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "payload": json.dumps(event.payload),
                "occurred_at": event.occurred_at.isoformat(),
            },
            maxlen=STREAM_MAX_LENGTH,
            approximate=True,
        )


async def relay_outbox_batch(
    session_factory: async_sessionmaker[AsyncSession],
    publisher: EventPublisher,
    *,
    limit: int = 100,
    clock: Clock,
) -> int:
    """Publish up to `limit` unpublished events. A publish failure leaves the whole batch
    unpublished (rolled back) so it is retried. Returns the number of events published."""
    async with session_factory() as session, session.begin():
        rows = (await session.execute(_CLAIM, {"limit": limit})).all()
        events = [
            OutboxEvent(
                id=row.id,
                type=row.type,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                payload=row.payload,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]
        for event in events:
            await publisher.publish(event)
        if events:
            await session.execute(_MARK, {"now": clock.now(), "ids": [e.id for e in events]})
    return len(events)


async def verify_audit_chain(session_factory: async_sessionmaker[AsyncSession]) -> list[int]:
    """Ids of audit rows whose chain link or hash does not verify (expected: none)."""
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM audit_verify_chain() WHERE NOT ok ORDER BY id")
        )
        broken = [int(row_id) for row_id in result.scalars()]
    if broken:
        logger.error("audit_chain_broken", first_broken_id=broken[0], count=len(broken))
    return broken
