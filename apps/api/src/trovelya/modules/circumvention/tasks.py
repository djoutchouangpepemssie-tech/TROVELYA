"""Anti-circumvention jobs run by the worker (workers/main.py)."""

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.circumvention import repository
from trovelya.shared.clock import Clock


async def purge_old_detections(
    sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock
) -> int:
    """Q36: detections older than `retention.circumvention_detection_days` (180, the window
    of the graded sanctions of 8.16) are deleted, those still awaiting review kept. A job:
    it commits."""
    async with sessionmaker() as db:
        days = await repository.setting_int(db, "retention.circumvention_detection_days")
        if days < 1:
            raise ValueError(
                f"retention.circumvention_detection_days must be at least 1 day, not {days}"
            )
        deleted = await repository.delete_detections_before(db, clock.now() - timedelta(days=days))
        await commit(db)
    return deleted


async def purge_old_detections_job(ctx: dict[str, Any]) -> int:
    return await purge_old_detections(ctx["sessionmaker"], clock=ctx["clock"])
