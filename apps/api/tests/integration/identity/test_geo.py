"""Geocoding routes `/v1/geo/*` (P1-T06a): signed-in, 30 per minute, 503 when unavailable."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_profile import T0, make_account
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.identity.adapters.geocoder import (
    FakeGeocoder,
    GeocoderUnavailableError,
    Place,
)
from trovelya.shared.clock import FixedClock


class DownGeocoder:
    async def search(self, q: str, *, limit: int = 5) -> list[Place]:
        raise GeocoderUnavailableError("ReadTimeout")

    async def reverse(self, lat: float, lon: float) -> Place | None:
        raise GeocoderUnavailableError("ReadTimeout")


def _client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, geocoder: Any
) -> AsyncClient:
    app = create_app(make_settings())
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = FixedClock(T0)
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    app.state.geocoder = geocoder
    client = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    )
    client.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
    return client


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> AsyncIterator[AsyncClient]:
    async with _client(sessionmaker, redis_client, FakeGeocoder()) as c:
        yield c


async def test_search_and_reverse(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker, completed=True)
    found = await client.get("/v1/geo/search", params={"q": "lyon"}, headers=account.headers)
    assert found.status_code == 200
    assert found.json() == {
        "data": [
            {
                "label": "Lyon 7e Arrondissement",
                "place_name": "Lyon 7e",
                "city": "Lyon",
                "postal_code": "69007",
                "district": "Lyon 7e",
                "country_code": "FR",
                "lat": 45.745,
                "lon": 4.842,
            }
        ]
    }
    near = await client.get(
        "/v1/geo/reverse", params={"lat": 48.86, "lon": 2.38}, headers=account.headers
    )
    assert near.status_code == 200 and near.json()["place_name"] == "Paris 11e"


async def test_requires_a_completed_profile(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    assert (await client.get("/v1/geo/search", params={"q": "lyon"})).status_code == 401
    incomplete = await make_account(sessionmaker)
    response = await client.get("/v1/geo/search", params={"q": "lyon"}, headers=incomplete.headers)
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/geo/search", {"q": "ly"}),
        ("/v1/geo/search", {"q": "x" * 201}),
        ("/v1/geo/reverse", {"lat": 91, "lon": 2}),
        ("/v1/geo/reverse", {"lat": 48, "lon": 181}),
    ],
)
async def test_invalid_queries_422(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    path: str,
    params: dict[str, Any],
) -> None:
    account = await make_account(sessionmaker, completed=True)
    assert (await client.get(path, params=params, headers=account.headers)).status_code == 422


async def test_rate_limit_30_per_minute_per_user(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker, completed=True)
    statuses = [
        (
            await client.get("/v1/geo/search", params={"q": "paris"}, headers=account.headers)
        ).status_code
        for _ in range(31)
    ]
    assert statuses == [200] * 30 + [429]
    # Another user is not affected.
    other = await make_account(sessionmaker, completed=True)
    response = await client.get("/v1/geo/search", params={"q": "paris"}, headers=other.headers)
    assert response.status_code == 200


async def test_geocoder_timeout_returns_503_problem(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    account = await make_account(sessionmaker, completed=True)
    async with _client(sessionmaker, redis_client, DownGeocoder()) as client:
        for path, params in (
            ("/v1/geo/search", {"q": "lyon"}),
            ("/v1/geo/reverse", {"lat": 45.7, "lon": 4.8}),
        ):
            response = await client.get(path, params=params, headers=account.headers)
            assert response.status_code == 503
            assert response.headers["content-type"].startswith("application/problem+json")
            assert response.json()["code"] == "service_unavailable"
