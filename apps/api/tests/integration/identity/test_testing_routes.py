"""The test-only session route exists in test and local, never on staging or production."""

from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from trovelya.core.csrf import SESSION_COOKIE
from trovelya.core.flags import FlagService
from trovelya.main import create_app


def _client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, env: str
) -> AsyncClient:
    app = create_app(make_settings(env=env))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    client.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
    return client


async def test_session_route_signs_in_a_new_member(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    async with _client(sessionmaker, redis_client, "test") as client:
        response = await client.post("/v1/_test/session", json={})
        assert response.status_code == 200
        assert client.cookies.get(SESSION_COOKIE)
        me = (await client.get("/v1/me")).json()
        assert me["id"] == response.json()["user_id"] and me["profile_completed"] is False

        client.cookies.clear()
        await client.post("/v1/_test/session", json={"completed": True})
        assert (await client.get("/v1/me")).json()["profile_completed"] is True
    async with sessionmaker() as db:
        assert (
            await db.scalar(
                text("SELECT count(*) FROM user_preferences WHERE user_id = :id"),
                {"id": response.json()["user_id"]},
            )
            == 1
        )


async def test_session_route_absent_outside_test_and_local(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    for env in ("staging", "production", "preview"):
        async with _client(sessionmaker, redis_client, env) as client:
            assert (await client.post("/v1/_test/session", json={})).status_code == 404, env
            staff = await client.post("/v1/_test/staff-enrolment", json={})
            assert staff.status_code == 404, env
