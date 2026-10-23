from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.idempotency import purge_idempotency_keys
from trovelya.shared.clock import SystemClock


async def test_purge_removes_keys_older_than_72_hours(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO idempotency_keys (key, method, path, request_hash, created_at) VALUES"
                " ('purge-old', 'POST', '/x', 'h', now() - interval '73 hours'),"
                " ('purge-new', 'POST', '/x', 'h', now() - interval '71 hours')"
            )
        )
        await session.commit()
    deleted = await purge_idempotency_keys(
        sessionmaker, clock=SystemClock(), ttl=timedelta(hours=72)
    )
    assert deleted >= 1
    async with sessionmaker() as session:
        keys = set(
            (
                await session.execute(
                    text("SELECT key FROM idempotency_keys WHERE key LIKE 'purge-%'")
                )
            ).scalars()
        )
    assert keys == {"purge-new"}
