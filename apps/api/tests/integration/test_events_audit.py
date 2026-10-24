from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.shared.audit import record_audit
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id


async def test_emit_event_rolled_back_not_persisted(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    aggregate_id = new_id()
    async with sessionmaker() as session:
        await emit_event(
            session,
            type="test.rolled_back",
            aggregate_type="test",
            aggregate_id=aggregate_id,
            payload={"a": 1},
        )
        await session.rollback()
    async with sessionmaker() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM outbox_events WHERE aggregate_id = :id"),
            {"id": aggregate_id},
        )
    assert count == 0


async def test_emit_event_committed_persisted(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    aggregate_id = new_id()
    async with sessionmaker() as session:
        event_id = await emit_event(
            session,
            type="test.committed",
            aggregate_type="test",
            aggregate_id=aggregate_id,
            payload={"a": 1},
        )
        await commit(session)
    async with sessionmaker() as session:
        row = (
            await session.execute(
                text("SELECT id, type, payload, published_at FROM outbox_events WHERE id = :id"),
                {"id": event_id},
            )
        ).one()
    assert row.id.version == 7
    assert row.type == "test.committed"
    assert row.payload == {"a": 1, "v": 1}
    assert row.published_at is None


async def test_emit_event_rejects_reserved_version_key(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import pytest

    async with sessionmaker() as session:
        with pytest.raises(ValueError, match="'v'"):
            await emit_event(
                session, type="t", aggregate_type="t", aggregate_id=new_id(), payload={"v": 2}
            )


async def test_record_audit_writes_chained_row(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    actor = new_id()
    async with sessionmaker() as session:
        row_id = await record_audit(
            session,
            actor_type="staff",
            actor_id=actor,
            action="settings.update",
            target_type="platform_settings",
            target_id="fees.x",
            reason="test",
            before={"value": 1},
            after={"value": 2},
            ip="203.0.113.7",
            request_id="req_x",
        )
        await commit(session)
    async with sessionmaker() as session:
        row = (
            await session.execute(text("SELECT * FROM audit_log WHERE id = :id"), {"id": row_id})
        ).one()
    assert row.actor_id == actor
    assert row.before == {"value": 1}
    assert row.after == {"value": 2}
    assert str(row.ip) == "203.0.113.7"
    assert len(row.hash) == 32


async def test_after_commit_callbacks_run_only_on_commit(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    from trovelya.core.db import on_commit

    calls: list[str] = []

    async def callback() -> None:
        calls.append("done")

    async with sessionmaker() as session:
        on_commit(session, callback)
        await session.rollback()
    assert calls == []

    async with sessionmaker() as session:
        on_commit(session, callback)
        await commit(session)
    assert calls == ["done"]
