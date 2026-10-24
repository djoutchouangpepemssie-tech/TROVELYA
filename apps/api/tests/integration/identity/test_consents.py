"""Consent records and the anonymous consent cookie (P1-T08a, sections 7.3 and 13.3)."""

import re
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_profile import T0, make_account
from trovelya.core.csrf import CSRF_COOKIE
from trovelya.core.email import open_email
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

ANON_COOKIE = "__Host-trv_anon"
WEB = "https://web.example.test"
SETTINGS = make_settings(web_origin=WEB)
ANALYTICS = {"purpose": "analytics", "granted": True, "policy_version": "cookies-2026-10"}


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    clock: FixedClock,
    queue: RecordingQueue,
) -> AsyncIterator[AsyncClient]:
    app = create_app(SETTINGS)
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = clock
    app.state.queue = queue
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


async def _csrf(client: AsyncClient) -> dict[str, str]:
    """An anonymous browser: the page fetches its CSRF token first (lib/api.ts)."""
    await client.get("/v1/csrf")
    return {"x-csrf-token": client.cookies[CSRF_COOKIE]}


_ROWS = (
    "SELECT user_id, anonymous_id, purpose, granted, policy_version, source FROM consents"
    " WHERE user_id IS NOT DISTINCT FROM coalesce(:user_id, user_id)"
    " AND anonymous_id IS NOT DISTINCT FROM coalesce(:anonymous_id, anonymous_id)"
    " ORDER BY created_at"
)


async def _rows(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    user_id: Any = None,
    anonymous_id: str | None = None,
) -> list[Any]:
    async with sessionmaker() as db:
        result = await db.execute(text(_ROWS), {"user_id": user_id, "anonymous_id": anonymous_id})
        return list(result.mappings())


async def test_consent_recorded_with_policy_version(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker, completed=True)
    response = await client.post("/v1/me/consents", headers=account.headers, json=ANALYTICS)
    assert response.status_code == 201, response.text
    [row] = await _rows(sessionmaker, user_id=account.id)
    assert dict(row) == {
        "user_id": account.id,
        "anonymous_id": None,
        "purpose": "analytics",
        "granted": True,
        "policy_version": "cookies-2026-10",
        "source": "web",
    }
    state = (await client.get("/v1/me/consents", headers=account.headers)).json()
    assert state["consents"] == [
        {
            "purpose": "analytics",
            "granted": True,
            "policy_version": "cookies-2026-10",
            "created_at": T0.isoformat().replace("+00:00", "Z"),
        }
    ]


async def test_latest_consent_wins(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    account = await make_account(sessionmaker, completed=True)
    await client.post("/v1/me/consents", headers=account.headers, json=ANALYTICS)
    clock.advance(timedelta(minutes=1))
    withdrawn = {**ANALYTICS, "granted": False}
    response = await client.post("/v1/me/consents", headers=account.headers, json=withdrawn)
    assert response.status_code == 201
    # Withdrawing keeps the history (proof of consent, RGPD art. 7).
    assert len(await _rows(sessionmaker, user_id=account.id)) == 2
    [latest] = response.json()["consents"]
    assert (latest["purpose"], latest["granted"]) == ("analytics", False)


async def test_incomplete_profile_can_record_consents(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    response = await client.post("/v1/me/consents", headers=account.headers, json=ANALYTICS)
    assert response.status_code == 201


async def test_anonymous_consent_sets_a_13_month_cookie(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    empty = await client.get("/v1/me/consents")
    assert empty.status_code == 200 and empty.json()["consents"] == []
    assert ANON_COOKIE not in empty.headers.get("set-cookie", "")

    response = await client.post("/v1/me/consents", headers=await _csrf(client), json=ANALYTICS)
    assert response.status_code == 201, response.text
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{ANON_COOKIE}=")
    assert "HttpOnly" in cookie and "Secure" in cookie and "Path=/" in cookie
    assert "Domain" not in cookie
    max_age = re.search(r"Max-Age=(\d+)", cookie)
    assert max_age is not None and int(max_age.group(1)) == 395 * 24 * 3600
    anonymous_id = client.cookies[ANON_COOKIE]
    [row] = await _rows(sessionmaker, anonymous_id=anonymous_id)
    assert row["user_id"] is None and row["granted"] is True

    # The same browser sees its choice; the cookie is kept, not reissued.
    again = await client.post(
        "/v1/me/consents", headers=await _csrf(client), json={**ANALYTICS, "granted": False}
    )
    assert ANON_COOKIE not in again.headers.get("set-cookie", "")
    state = (await client.get("/v1/me/consents")).json()["consents"]
    assert [(c["purpose"], c["granted"]) for c in state] == [("analytics", False)]


async def test_forged_anonymous_cookie_is_replaced(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    client.cookies.set(ANON_COOKIE, "x" * 300)
    response = await client.post("/v1/me/consents", headers=await _csrf(client), json=ANALYTICS)
    assert response.status_code == 201
    assert response.headers["set-cookie"].startswith(f"{ANON_COOKIE}=")
    assert await _rows(sessionmaker, anonymous_id="x" * 300) == []


async def test_consent_needs_csrf_even_without_session(client: AsyncClient) -> None:
    """Otherwise another site could record a consent in the visitor's browser."""
    response = await client.post("/v1/me/consents", json=ANALYTICS)
    assert response.status_code == 403 and response.json()["code"] == "csrf_failed"


@pytest.mark.parametrize(
    "change",
    [
        {"purpose": "terms"},
        {"purpose": "cookies"},
        {"policy_version": ""},
        {"policy_version": "v" * 65},
        {"granted": None},
    ],
)
async def test_invalid_consent_422(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, change: dict[str, Any]
) -> None:
    account = await make_account(sessionmaker, completed=True)
    response = await client.post(
        "/v1/me/consents", headers=account.headers, json={**ANALYTICS, **change}
    )
    assert response.status_code == 422


async def test_anonymous_consent_attached_on_login(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    await client.post("/v1/me/consents", headers=await _csrf(client), json=ANALYTICS)
    anonymous_id = client.cookies[ANON_COOKIE]

    email = f"{new_id().hex}@example.org"
    await client.post("/v1/auth/magic-link", json={"email": email})
    message = open_email(queue.jobs[-1][1][0], settings=SETTINGS)
    found = re.search(r"#token=([A-Za-z0-9_-]+)", message.text)
    assert found is not None
    signed_in = await client.post("/v1/auth/magic-link/verify", json={"token": found.group(1)})
    assert signed_in.status_code == 200, signed_in.text
    user_id = signed_in.json()["user_id"]

    [row] = await _rows(sessionmaker, anonymous_id=anonymous_id)
    assert str(row["user_id"]) == user_id
    headers = await _csrf(client)
    state = (await client.get("/v1/me/consents", headers=headers)).json()["consents"]
    assert [(c["purpose"], c["granted"]) for c in state] == [("analytics", True)]


async def test_active_purposes_come_from_the_settings(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    """Q15: the banner shows only when a non-essential purpose is active (none in P1)."""
    assert (await client.get("/v1/me/consents")).json()["active_purposes"] == []
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO platform_settings (key, value, description)"
                " VALUES ('consent.active_purposes', '[\"analytics\", \"nope\"]', 'test')"
            )
        )
        await db.commit()
    try:
        state = (await client.get("/v1/me/consents")).json()
        assert state["active_purposes"] == ["analytics"]
    finally:
        async with sessionmaker() as db:
            await db.execute(
                text("DELETE FROM platform_settings WHERE key = 'consent.active_purposes'")
            )
            await db.commit()
