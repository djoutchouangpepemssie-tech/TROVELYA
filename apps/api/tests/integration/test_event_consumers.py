"""Idempotent consumers of the domain event stream (section 5.6, ADR-0007, P1-T02c part 3)."""

from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.shared.events import OutboxEvent, Subscription
from trovelya.shared.ids import new_id
from trovelya.workers.consumers import consume_events, ensure_group
from trovelya.workers.outbox_relay import RedisStreamPublisher

STREAM = "test:events"


def _event(type_: str = "session.created") -> OutboxEvent:
    return OutboxEvent(
        id=new_id(),
        type=type_,
        aggregate_type="user",
        aggregate_id=new_id(),
        payload={"session_id": str(new_id()), "v": 1},
        occurred_at=datetime(2026, 10, 24, 12, tzinfo=UTC),
    )


async def test_handler_runs_once_and_message_is_acked(
    redis_client: Redis, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    seen: list[UUID] = []

    async def handler(_: AsyncSession, event: OutboxEvent) -> None:
        seen.append(event.id)

    subscriptions = [Subscription("test.recorder", "session.created", handler)]
    await ensure_group(redis_client, stream=STREAM)
    event = _event()
    await RedisStreamPublisher(redis_client, stream=STREAM).publish(event)
    await RedisStreamPublisher(redis_client, stream=STREAM).publish(_event("other.event"))

    processed = await consume_events(
        redis_client, sessionmaker, subscriptions, consumer_name="w1", stream=STREAM
    )
    assert processed == 2
    assert seen == [event.id]
    again = await consume_events(
        redis_client, sessionmaker, subscriptions, consumer_name="w1", stream=STREAM
    )
    assert again == 0
    pending = await redis_client.xpending(STREAM, "trovelya")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert pending["pending"] == 0


async def test_failed_handler_is_retried_and_redelivery_is_idempotent(
    redis_client: Redis, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    calls: list[UUID] = []
    fail = {"next": True}

    async def flaky(_: AsyncSession, event: OutboxEvent) -> None:
        calls.append(event.id)
        if fail["next"]:
            fail["next"] = False
            raise RuntimeError("boom")

    subscriptions = [Subscription("test.flaky", "session.created", flaky)]
    await ensure_group(redis_client, stream=STREAM)
    event = _event()
    await RedisStreamPublisher(redis_client, stream=STREAM).publish(event)

    assert (
        await consume_events(
            redis_client, sessionmaker, subscriptions, consumer_name="w1", stream=STREAM
        )
        == 0
    )
    # Another worker takes over the stale message (here: immediately).
    assert (
        await consume_events(
            redis_client,
            sessionmaker,
            subscriptions,
            consumer_name="w2",
            stream=STREAM,
            claim_idle_ms=0,
        )
        == 1
    )
    assert calls == [event.id, event.id]

    # A duplicate delivery (at least once) does not run the handler again.
    await RedisStreamPublisher(redis_client, stream=STREAM).publish(event)
    await consume_events(
        redis_client, sessionmaker, subscriptions, consumer_name="w2", stream=STREAM
    )
    assert calls == [event.id, event.id]


async def test_ensure_group_is_idempotent(redis_client: Redis) -> None:
    await ensure_group(redis_client, stream=STREAM)
    await ensure_group(redis_client, stream=STREAM)
