"""`python -m trovelya.scripts.seed_catalog`, run after the migrations at each deployment."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import make_settings
from trovelya.modules.catalog.service import seed
from trovelya.scripts import seed_catalog


async def test_script_loads_the_catalog(
    migrated_url: str,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = make_settings(database_url=migrated_url)
    monkeypatch.setattr(seed_catalog, "get_settings", lambda: settings)
    assert await seed_catalog._run() == 0  # pyright: ignore[reportPrivateUsage]
    assert await seed_catalog._run() == 0  # pyright: ignore[reportPrivateUsage]
    assert "430 catégories" in capsys.readouterr().out
    async with engine.connect() as conn:
        count = await conn.execute(text("SELECT count(*) FROM categories WHERE is_active"))
        assert count.scalar_one() >= 430


async def test_script_refuses_an_invalid_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(seed_catalog, "load_seed", lambda: seed.parse_seed({"version": 2}))
    assert await seed_catalog._run() == 1  # pyright: ignore[reportPrivateUsage]
    assert "Graine refusée : version 2" in capsys.readouterr().err
