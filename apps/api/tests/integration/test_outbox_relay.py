import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.shared.clock import FixedClock
from trovelya.shared.events import InMemoryPublisher, OutboxEvent, consume_once, emit_event
from trovelya.shared.ids import new_id
from trovelya.workers.outbox_relay import (
    RedisStreamPublisher,
    oldest_unpublished_age_seconds,
    relay_outbox_batch,
    verify_audit_chain,
)

CLOCK = FixedClock(datetime(2026, 10, 23, 12, 0, tzinfo=UTC))


async def _emit(sm: async_sessionmaker[AsyncSession], aggregate_id: UUID, n: int = 1) -> list[UUID]:
    async with sm() as session:
        ids = [
            await emit_event(
                session,
                type="test.relay",
                aggregate_type="test",
                aggregate_id=aggregate_id,
                payload={"n": i},
            )
            for i in range(n)
        ]
        await commit(session)
    return ids


async def _drain(sm: async_sessionmaker[AsyncSession], publisher: InMemoryPublisher) -> None:
    while await relay_outbox_batch(sm, publisher, clock=CLOCK) > 0:
        pass


def _mine(publisher: InMemoryPublisher, aggregate_id: UUID) -> list[OutboxEvent]:
    return [e for e in publisher.events if e.aggregate_id == aggregate_id]


async def test_rolled_back_event_never_published(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    aggregate_id = new_id()
    async with sessionmaker() as session:
        await emit_event(
            session, type="test.relay", aggregate_type="test", aggregate_id=aggregate_id, payload={}
        )
        await session.rollback()
    publisher = InMemoryPublisher()
    await _drain(sessionmaker, publisher)
    assert _mine(publisher, aggregate_id) == []


async def test_relay_publishes_in_id_order(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    aggregate_id = new_id()
    ids = await _emit(sessionmaker, aggregate_id, n=5)
    publisher = InMemoryPublisher()
    await _drain(sessionmaker, publisher)
    assert [e.id for e in _mine(publisher, aggregate_id)] == ids
    assert [e.payload["n"] for e in _mine(publisher, aggregate_id)] == [0, 1, 2, 3, 4]


async def test_relay_marks_published(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    aggregate_id = new_id()
    await _emit(sessionmaker, aggregate_id)
    await _drain(sessionmaker, InMemoryPublisher())
    async with sessionmaker() as session:
        published_at = await session.scalar(
            text("SELECT published_at FROM outbox_events WHERE aggregate_id = :a"),
            {"a": aggregate_id},
        )
    assert published_at == CLOCK.now()


class _FailingPublisher(InMemoryPublisher):
    async def publish(self, event: OutboxEvent) -> None:
        raise ConnectionError("broker down")


async def test_publish_failure_keeps_batch_unpublished(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    aggregate_id = new_id()
    await _emit(sessionmaker, aggregate_id, n=2)
    with pytest.raises(ConnectionError):
        await relay_outbox_batch(sessionmaker, _FailingPublisher(), clock=CLOCK)
    async with sessionmaker() as session:
        unpublished = await session.scalar(
            text(
                "SELECT count(*) FROM outbox_events"
                " WHERE aggregate_id = :a AND published_at IS NULL"
            ),
            {"a": aggregate_id},
        )
    assert unpublished == 2


class _SlowPublisher(InMemoryPublisher):
    async def publish(self, event: OutboxEvent) -> None:
        await asyncio.sleep(0.01)
        await super().publish(event)


async def test_two_relays_do_not_share_rows(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    await _drain(sessionmaker, InMemoryPublisher())  # start from an empty backlog
    aggregate_id = new_id()
    await _emit(sessionmaker, aggregate_id, n=40)
    first, second = _SlowPublisher(), _SlowPublisher()

    async def run(publisher: InMemoryPublisher) -> None:
        while await relay_outbox_batch(sessionmaker, publisher, limit=5, clock=CLOCK) > 0:
            pass

    await asyncio.gather(run(first), run(second))
    published = [e.id for e in _mine(first, aggregate_id) + _mine(second, aggregate_id)]
    assert len(published) == 40
    assert len(set(published)) == 40
    assert _mine(first, aggregate_id) and _mine(second, aggregate_id)


async def test_consume_once_idempotent(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    event_id = new_id()
    calls: list[UUID] = []

    async def handler() -> None:
        calls.append(event_id)

    for _ in range(2):
        async with sessionmaker() as session:
            await consume_once(session, "test-consumer", event_id, handler)
            await commit(session)
    assert calls == [event_id]


async def test_consume_once_rolled_back_can_retry(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    event_id = new_id()
    calls: list[UUID] = []

    async def handler() -> None:
        calls.append(event_id)

    async with sessionmaker() as session:
        assert await consume_once(session, "test-consumer", event_id, handler) is True
        await session.rollback()
    async with sessionmaker() as session:
        assert await consume_once(session, "test-consumer", event_id, handler) is True
        await commit(session)
    assert len(calls) == 2


async def test_redis_stream_publisher(redis_client: Redis) -> None:
    publisher = RedisStreamPublisher(redis_client, stream="trv:test-events")
    event = OutboxEvent(
        id=new_id(),
        type="test.stream",
        aggregate_type="test",
        aggregate_id=new_id(),
        payload={"n": 1, "v": 1},
        occurred_at=CLOCK.now(),
    )
    await publisher.publish(event)
    entries = await redis_client.xrange("trv:test-events")  # pyright: ignore[reportUnknownMemberType]
    assert len(entries) == 1
    fields = entries[0][1]
    assert fields[b"id"] == str(event.id).encode()
    assert fields[b"type"] == b"test.stream"


async def test_verify_audit_chain_reports_broken_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    assert await verify_audit_chain(sessionmaker) == []


async def test_oldest_unpublished_age(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    await _drain(sessionmaker, InMemoryPublisher())
    assert await oldest_unpublished_age_seconds(sessionmaker, clock=CLOCK) == 0.0

    [event_id] = await _emit(sessionmaker, new_id())
    async with sessionmaker() as session:
        occurred_at = (
            await session.execute(
                text("SELECT occurred_at FROM outbox_events WHERE id = :id"), {"id": event_id}
            )
        ).scalar_one()
    later = FixedClock(occurred_at + timedelta(seconds=30))
    assert await oldest_unpublished_age_seconds(sessionmaker, clock=later) == 30.0

    await _drain(sessionmaker, InMemoryPublisher())
    assert await oldest_unpublished_age_seconds(sessionmaker, clock=later) == 0.0
