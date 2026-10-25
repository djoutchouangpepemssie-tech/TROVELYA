"""The test-only session route exists in test and local, never on staging or production."""

from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from trovelya.core.csrf import CSRF_COOKIE, SESSION_COOKIE
from trovelya.core.flags import FlagService
from trovelya.main import create_app


class _NoQueue:
    """Jobs (e-mails, exports) are not run in these tests."""

    async def enqueue_job(self, function: str, *args: object) -> None:
        return None


def _client(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    env: str,
    **settings: object,
) -> AsyncClient:
    app = create_app(make_settings(env=env, **settings))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    app.state.queue = _NoQueue()
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
            link = await client.post("/v1/_test/magic-link", json={"email": "a@example.org"})
            assert link.status_code == 404, env
            for path in (
                "/v1/_test/step-up-link",
                "/v1/_test/email-change-link",
                "/v1/_test/flag-allow",
            ):
                answer = await client.post(path, json={"new_email": "b@example.org"})
                assert answer.status_code == 404, (env, path)


async def _with_csrf(client: AsyncClient) -> None:
    """Unsafe calls of a signed-in browser echo the CSRF cookie (double submit)."""
    await client.get("/v1/csrf")
    client.headers["x-csrf-token"] = client.cookies[CSRF_COOKIE]


async def test_session_route_can_skip_the_strong_proof(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    """`strong: false` gives a session whose sensitive actions ask for step-up first."""
    async with _client(sessionmaker, redis_client, "test") as client:
        await client.post("/v1/_test/session", json={"completed": True, "strong": False})
        await _with_csrf(client)
        refused = await client.post("/v1/me/data-export")
        assert refused.status_code == 403 and refused.json()["code"] == "step_up_required"


async def test_step_up_and_email_change_links(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    """The links the e-mails would carry, for the signed-in member (e2e of /confirmer pages)."""
    async with _client(sessionmaker, redis_client, "test") as client:
        assert (await client.post("/v1/_test/step-up-link", json={})).status_code == 401
        await client.post("/v1/_test/session", json={"completed": True, "strong": False})
        await _with_csrf(client)
        step_up = (await client.post("/v1/_test/step-up-link", json={})).json()["link"]
        assert "/fr/confirmer#token=" in step_up
        token = step_up.split("#token=")[1]
        assert (
            await client.post("/v1/auth/step-up/verify", json={"token": token})
        ).status_code == 204
        assert (await client.post("/v1/me/data-export")).status_code == 202

        change = await client.post(
            "/v1/_test/email-change-link", json={"new_email": "nouvelle@example.org"}
        )
        link = change.json()["link"]
        assert "/fr/compte/email/confirmer#token=" in link
        verified = await client.post(
            "/v1/auth/email-change/verify", json={"token": link.split("#token=")[1]}
        )
        assert verified.status_code == 204
        assert (await client.get("/v1/me")).json()["email"] == "nouvelle@example.org"


async def test_flag_allow_opens_a_flag_to_one_member(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    async with _client(sessionmaker, redis_client, "test") as client:
        await client.post("/v1/_test/session", json={"completed": True})
        await _with_csrf(client)
        try:
            allowed = await client.post("/v1/_test/flag-allow", json={"key": "auth.passkeys"})
            assert allowed.status_code == 204
            assert (await client.get("/v1/me/passkeys")).status_code == 200
            client.cookies.clear()
            del client.headers["x-csrf-token"]
            await client.post("/v1/_test/session", json={"completed": True})
            assert (await client.get("/v1/me/passkeys")).status_code == 404
        finally:
            async with sessionmaker() as db:
                await db.execute(text("DELETE FROM feature_flags WHERE key = 'auth.passkeys'"))
                await db.commit()
            await redis_client.delete("flag:auth.passkeys")


async def test_flag_allow_keeps_the_default_and_lists_a_member_once(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    """A flag first written by the route stays at its configured default for everyone else."""
    key = "test.default_on"
    async with _client(
        sessionmaker, redis_client, "test", feature_flags_default={key: True}
    ) as client:
        response = await client.post("/v1/_test/session", json={"completed": True})
        user_id = response.json()["user_id"]
        await _with_csrf(client)
        try:
            for _ in range(2):
                allowed = await client.post("/v1/_test/flag-allow", json={"key": key})
                assert allowed.status_code == 204
            async with sessionmaker() as db:
                row = (
                    await db.execute(
                        text(
                            "SELECT enabled, CAST(allow_user_ids AS text[]) AS ids"
                            " FROM feature_flags WHERE key = :key"
                        ),
                        {"key": key},
                    )
                ).one()
            assert row.enabled is True
            assert row.ids == [user_id]
        finally:
            async with sessionmaker() as db:
                await db.execute(text("DELETE FROM feature_flags WHERE key = :key"), {"key": key})
                await db.commit()
            await redis_client.delete("flag:" + key)
