"""Fixtures of the catalog's integration tests: the seed loaded once, a client on the API
(verticals off). A test module may define its own `client` (another flag, another app)."""

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.catalog.test_categories_api import (
    catalog_client,
    seeded,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture shared here)
)


@pytest.fixture
async def client(
    seeded: None,  # noqa: F811
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
) -> AsyncIterator[AsyncClient]:
    async with await catalog_client(sessionmaker, redis_client, verticals=False) as c:
        yield c
