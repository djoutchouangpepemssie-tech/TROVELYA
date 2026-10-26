"""`python -m trovelya.scripts.seed_catalog`, run after the migrations at each deployment."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.conftest import make_settings
from tests.integration.conftest import alembic_config
from trovelya.core.db import make_engine
from trovelya.modules.catalog.service import seed
from trovelya.modules.catalog.service.seed import CatalogSeed
from trovelya.scripts import seed_catalog

_run = seed_catalog._run  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
async def empty_database(engine: AsyncEngine, migrated_url: str) -> AsyncIterator[str]:
    """A database of its own, migrated and never seeded."""
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("CREATE DATABASE seed_script"))
    url = migrated_url.rsplit("/", 1)[0] + "/seed_script"
    await asyncio.to_thread(command.upgrade, alembic_config(url), "head")
    yield url
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("DROP DATABASE seed_script WITH (FORCE)"))


async def test_script_loads_the_catalog_and_commits(
    empty_database: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = make_settings(database_url=empty_database)
    monkeypatch.setattr(seed_catalog, "get_settings", lambda: settings)
    assert await _run() == 0
    assert await _run() == 0
    assert "430 catégories" in capsys.readouterr().out
    engine = make_engine(empty_database)
    try:
        async with engine.connect() as conn:
            counts = await conn.execute(
                text("SELECT (SELECT count(*) FROM categories), (SELECT count(*) FROM brands)")
            )
            assert tuple(counts.one()) == (430, 372)
    finally:
        await engine.dispose()


async def test_script_refuses_an_invalid_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(seed_catalog, "load_seed", lambda: seed.parse_seed({"version": 2}))
    assert await _run() == 1
    assert "Graine refusée : version 2" in capsys.readouterr().err


async def test_script_reports_a_commit_time_violation(
    empty_database: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def collide(db: AsyncSession, seed: CatalogSeed) -> None:
        raise IntegrityError("COMMIT", None, Exception("categories_path_key"))

    settings = make_settings(database_url=empty_database)
    monkeypatch.setattr(seed_catalog, "get_settings", lambda: settings)
    monkeypatch.setattr(seed_catalog, "apply_seed", collide)
    assert await _run() == 1
    assert "chemin déjà pris" in capsys.readouterr().err
