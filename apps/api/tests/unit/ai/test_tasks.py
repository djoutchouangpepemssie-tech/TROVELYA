"""The purge of the AI calls' log is scheduled by the worker (plan Q46)."""

import pytest

from tests.conftest import make_settings
from trovelya.modules.ai import tasks


def test_purge_scheduled_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    # The worker reads its settings when imported: the tests' own.
    monkeypatch.setattr("trovelya.core.config.get_settings", make_settings)
    from trovelya.workers.main import WorkerSettings

    assert tasks.purge_old_calls_job in {job.coroutine for job in WorkerSettings.cron_jobs}
