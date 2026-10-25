"""Sign-in methods offered to a visitor (P1-T12a): the screens hide what is off."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_profile import make_account
from trovelya.core.csrf import SESSION_COOKIE
from trovelya.core.flags import CACHE_PREFIX, FlagService
from trovelya.main import create_app


async def _methods(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    flags: dict[str, bool],
    **settings: Any,
) -> dict[str, Any]:
    app = create_app(make_settings(**settings))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.flags = FlagService(sessionmaker, redis_client, flags)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        client.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        response = await client.get("/v1/auth/methods")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("passkeys", [True, False])
async def test_methods_follow_the_flags(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, passkeys: bool
) -> None:
    methods = await _methods(sessionmaker, redis_client, {"auth.passkeys": passkeys})
    assert methods == {
        "magic_link": True,
        "magic_link_ttl_min": 15,
        "passkey": passkeys,
        "google": False,
        "apple": False,
    }


async def test_link_lifetime_follows_the_platform_setting(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    """The screen says how long the link lasts: the same figure as the e-mail (PARAM)."""
    key = "auth.magic_link_ttl_min"
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE platform_settings SET value = '30' WHERE key = :k"), {"k": key}
        )
        await db.commit()
    try:
        methods = await _methods(sessionmaker, redis_client, {})
        assert methods["magic_link_ttl_min"] == 30
    finally:
        async with sessionmaker() as db:
            await db.execute(
                text("UPDATE platform_settings SET value = '15' WHERE key = :k"), {"k": key}
            )
            await db.commit()


async def test_provider_needs_flag_and_credentials(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    # Flag on but no credentials: hidden (the start route would answer 404).
    methods = await _methods(sessionmaker, redis_client, {"auth.oauth_google": True})
    assert methods["google"] is False
    # Flag and credentials: shown.
    methods = await _methods(
        sessionmaker,
        redis_client,
        {"auth.oauth_google": True},
        oauth_google_client_id="client-id.apps.example",
        oauth_google_client_secret="ci-only-secret-key-google-0123456789",
    )
    assert methods["google"] is True


async def test_passkeys_follow_the_flag_allow_list(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    """Flag off for all but the allowed members (beta testers): they see and manage passkeys."""
    allowed = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO feature_flags (key, enabled, allow_user_ids)"
                " VALUES ('auth.passkeys', false, ARRAY[CAST(:id AS uuid)])"
            ),
            {"id": allowed.id},
        )
        await db.commit()
    await redis_client.delete(CACHE_PREFIX + "auth.passkeys")
    try:
        app = create_app(make_settings())
        app.state.sessionmaker = sessionmaker
        app.state.redis = redis_client
        app.state.flags = FlagService(sessionmaker, redis_client, {})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            client.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
            for account, expected in ((allowed, True), (other, False)):
                methods = (await client.get("/v1/auth/methods", headers=account.headers)).json()
                assert methods["passkey"] is expected
                listed = await client.get("/v1/me/passkeys", headers=account.headers)
                assert listed.status_code == (200 if expected else 404)
                options = await client.post("/v1/auth/step-up/options", headers=account.headers)
                assert (options.status_code != 404) is expected
            # Signed out: the flag as everyone sees it.
            assert (await client.get("/v1/auth/methods")).json()["passkey"] is False
    finally:
        async with sessionmaker() as db:
            await db.execute(text("DELETE FROM feature_flags WHERE key = 'auth.passkeys'"))
            await db.commit()
        await redis_client.delete(CACHE_PREFIX + "auth.passkeys")


async def test_a_dead_session_cookie_still_gets_the_methods(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    """A forged or revoked cookie must not lock a visitor out of the sign-in screen."""
    account = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        await db.execute(text("DELETE FROM sessions WHERE user_id = :id"), {"id": account.id})
        await db.commit()
    app = create_app(make_settings())
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.flags = FlagService(sessionmaker, redis_client, {"auth.passkeys": True})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        client.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        for cookie in (account.headers["cookie"], f"{SESSION_COOKIE}=forged"):
            response = await client.get("/v1/auth/methods", headers={"cookie": cookie})
            assert response.status_code == 200, cookie
            assert response.json()["passkey"] is True
