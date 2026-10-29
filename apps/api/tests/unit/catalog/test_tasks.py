"""The catalog's jobs are scheduled by the worker and hand it their result (P2-T04d)."""

from datetime import UTC, datetime
from typing import Any

import pytest

from tests.conftest import make_settings
from trovelya.modules.catalog import tasks
from trovelya.shared.clock import FixedClock


def test_daily_jobs_scheduled(monkeypatch: pytest.MonkeyPatch) -> None:
    # The worker reads its settings when imported: the tests' own.
    monkeypatch.setattr("trovelya.core.config.get_settings", make_settings)
    from trovelya.workers.main import WorkerSettings

    scheduled = {job.coroutine for job in WorkerSettings.cron_jobs}
    assert tasks.expire_listings_job in scheduled


async def test_expire_job_runs_the_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    async def expire_listings(sessionmaker: object, *, clock: object) -> int:
        called.update(sessionmaker=sessionmaker, clock=clock)
        return 3

    monkeypatch.setattr(tasks, "expire_listings", expire_listings)
    clock = FixedClock(datetime(2026, 10, 29, tzinfo=UTC))
    ctx = {"sessionmaker": object(), "clock": clock}
    assert await tasks.expire_listings_job(ctx) == 3
    assert called == {"sessionmaker": ctx["sessionmaker"], "clock": clock}
