"""Consumers of the domain event stream (section 5.6, ADR-0007).

The outbox relay publishes committed events to the Redis stream `trv:events`. Workers read it
as one consumer group: each message goes to one worker, which runs every subscription for its
type, each in its own transaction through `consume_once` (a subscription never runs twice for
the same event, even when the stream delivers it again), then acknowledges the message.

A message whose handler failed stays pending; after `claim_idle_ms` any worker claims it and
tries again, so a crash or a redeploy loses nothing.
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.shared.events import OutboxEvent, Subscription, consume_once
from trovelya.workers.outbox_relay import EVENTS_STREAM

logger = structlog.get_logger(__name__)

GROUP = "trovelya"
CLAIM_IDLE_MS = 60_000


async def ensure_group(redis: Redis, *, stream: str = EVENTS_STREAM) -> None:
    """Create the consumer group once; it starts with the events published from now on."""
    try:
        await redis.xgroup_create(stream, GROUP, id="$", mkstream=True)  # pyright: ignore[reportUnknownMemberType]
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _decode(fields: dict[Any, Any]) -> OutboxEvent:
    data = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in fields.items()
    }
    return OutboxEvent(
        id=UUID(data["id"]),
        type=data["type"],
        aggregate_type=data["aggregate_type"],
        aggregate_id=UUID(data["aggregate_id"]),
        payload=json.loads(data["payload"]),
        occurred_at=datetime.fromisoformat(data["occurred_at"]),
    )


async def _handle(
    sessionmaker: async_sessionmaker[AsyncSession],
    subscriptions: list[Subscription],
    event: OutboxEvent,
) -> None:
    for subscription in subscriptions:
        if subscription.event_type != event.type:
            continue
        async with sessionmaker() as db:

            async def run(db: AsyncSession = db, sub: Subscription = subscription) -> None:
                await sub.handler(db, event)

            await consume_once(db, subscription.consumer, event.id, run)
            await commit(db)


async def consume_events(
    redis: Redis,
    sessionmaker: async_sessionmaker[AsyncSession],
    subscriptions: list[Subscription],
    *,
    consumer_name: str,
    stream: str = EVENTS_STREAM,
    count: int = 100,
    claim_idle_ms: int = CLAIM_IDLE_MS,
) -> int:
    """Process stale pending messages, then new ones. Returns the number acknowledged."""
    claimed = await redis.xautoclaim(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        stream, GROUP, consumer_name, min_idle_time=claim_idle_ms, start_id="0-0", count=count
    )
    batches: list[Any] = [claimed[1]]  # pyright: ignore[reportUnknownArgumentType]
    fresh = await redis.xreadgroup(GROUP, consumer_name, {stream: ">"}, count=count)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    batches += [messages for _, messages in fresh]  # pyright: ignore[reportUnknownVariableType]

    acknowledged = 0
    for messages in batches:
        for message_id, fields in messages:
            try:
                await _handle(sessionmaker, subscriptions, _decode(fields))
            except Exception as exc:  # noqa: BLE001 — stays pending, retried after claim_idle_ms
                logger.error("event.consumer_failed", error=type(exc).__name__)
                continue
            await redis.xack(stream, GROUP, message_id)  # pyright: ignore[reportUnknownMemberType]
            acknowledged += 1
    return acknowledged
