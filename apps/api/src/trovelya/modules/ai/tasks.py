"""AI jobs run by the worker (workers/main.py)."""

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.ai import repository
from trovelya.shared.clock import Clock


async def purge_old_calls(sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock) -> int:
    """Q46: the calls logged more than `retention.ai_suggestion_days` ago (365) are erased.
    A job: it commits."""
    async with sessionmaker() as db:
        days = await repository.setting_int(db, "retention.ai_suggestion_days")
        if days < 1:
            raise ValueError(f"retention.ai_suggestion_days must be at least 1 day, not {days}")
        deleted = await repository.delete_calls_before(db, clock.now() - timedelta(days=days))
        await commit(db)
    return deleted


async def purge_old_calls_job(ctx: dict[str, Any]) -> int:
    return await purge_old_calls(ctx["sessionmaker"], clock=ctx["clock"])
