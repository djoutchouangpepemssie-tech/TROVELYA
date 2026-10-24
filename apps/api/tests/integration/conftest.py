"""Integration fixtures: one real PostgreSQL container (our image) per test session."""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from trovelya.core.db import make_engine, make_sessionmaker

API_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_IMAGE = os.environ.get("TEST_POSTGRES_IMAGE", "trovelya/postgres:17")


def alembic_config(database_url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
async def migrated_url(database_url: str) -> str:
    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")
    return database_url


@pytest.fixture(scope="session")
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)
