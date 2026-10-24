"""Opaque server-side sessions (P1-T02b, ADR-0008, section 13.2)."""

import base64
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import Response

from tests.conftest import TEST_SECRET, make_settings
from trovelya.core.csrf import CSRF_COOKIE, SESSION_COOKIE, issue_csrf_token
from trovelya.main import create_app
from trovelya.modules.identity.service import (
    IssuedSession,
    SessionPolicy,
    create_session,
    resolve_session,
    rotate_session,
    set_session_cookie,
)
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
POLICY = SessionPolicy(
    web_ttl=timedelta(days=30),
    admin_ttl=timedelta(hours=12),
    idle=timedelta(days=14),
    touch_interval=timedelta(minutes=5),
)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


async def _user(sessionmaker: async_sessionmaker[AsyncSession], status: str = "active") -> UUID:
    user_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, username, display_name, status)"
                " VALUES (:id, :email, :username, 'Membre', CAST(:status AS user_status))"
            ),
            {
                "id": user_id,
                "email": f"{user_id.hex}@example.org",
                "username": f"u_{user_id.hex[-8:]}",
                "status": status,
            },
        )
        await db.commit()
    return user_id


async def _session(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: UUID, clock: FixedClock
) -> IssuedSession:
    async with sessionmaker() as db:
        issued = await create_session(
            db,
            user_id=user_id,
            kind="web",
            ip="203.0.113.7",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Chrome/130.0",
            country="FR",
            strong=True,
            policy=POLICY,
            clock=clock,
        )
        await db.commit()
    return issued


async def _resolve(
    sessionmaker: async_sessionmaker[AsyncSession], token: str, clock: FixedClock
) -> Any:
    async with sessionmaker() as db:
        current = await resolve_session(db, token, policy=POLICY, clock=clock)
        await db.commit()
    return current


def _headers(token: str, *, unsafe: bool = False) -> dict[str, str]:
    if not unsafe:
        return {"cookie": f"{SESSION_COOKIE}={token}"}
    csrf = issue_csrf_token(TEST_SECRET)
    return {"cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}", "x-csrf-token": csrf}


def _client(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    clock: FixedClock,
    **settings: object,
) -> AsyncClient:
    app = create_app(make_settings(**settings))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis
    app.state.clock = clock
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    )


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> AsyncIterator[AsyncClient]:
    async with _client(sessionmaker, redis_client, clock) as c:
        yield c


# --- Tokens and cookie ---------------------------------------------------------------------


async def test_token_256_bits_and_only_hash_stored(
    sessionmaker: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    issued = await _session(sessionmaker, await _user(sessionmaker), clock)
    raw = base64.urlsafe_b64decode(issued.token + "=" * (-len(issued.token) % 4))
    assert len(raw) == 32
    async with sessionmaker() as db:
        row = (
            await db.execute(
                text(
                    "SELECT token_hash, row_to_json(sessions)::text AS everything FROM sessions"
                    " WHERE id = :id"
                ),
                {"id": issued.session_id},
            )
        ).one()
    assert bytes(row.token_hash) == hashlib.sha256(issued.token.encode()).digest()
    assert issued.token not in row.everything


def test_cookie_attributes(clock: FixedClock) -> None:
    issued = IssuedSession(token="tok", session_id=new_id(), expires_at=T0 + timedelta(days=30))
    response = Response()
    set_session_cookie(response, issued, clock=clock)
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=tok;")
    for attribute in ("HttpOnly", "Secure", "Path=/", "SameSite=lax", "Max-Age=2592000"):
        assert attribute in cookie
    assert "Domain" not in cookie


# --- Expiry ------------------------------------------------------------------------------


async def test_absolute_expiry_30_days(
    sessionmaker: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    issued = await _session(sessionmaker, await _user(sessionmaker), clock)
    for _ in range(2):  # activity every 13 days keeps the idle timer alive
        clock.advance(timedelta(days=13))
        assert await _resolve(sessionmaker, issued.token, clock) is not None
    clock.advance(timedelta(days=4))  # day 30 + a little
    assert await _resolve(sessionmaker, issued.token, clock) is None


async def test_idle_expiry_14_days(
    sessionmaker: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    issued = await _session(sessionmaker, await _user(sessionmaker), clock)
    clock.advance(timedelta(days=14) - timedelta(seconds=1))
    assert await _resolve(sessionmaker, issued.token, clock) is not None
    clock.advance(timedelta(days=14) + timedelta(seconds=1))
    assert await _resolve(sessionmaker, issued.token, clock) is None


async def _last_used(sessionmaker: async_sessionmaker[AsyncSession], session_id: UUID) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(
            text("SELECT last_used_at FROM sessions WHERE id = :id"), {"id": session_id}
        )


async def test_last_used_at_throttled_5_min(
    sessionmaker: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    issued = await _session(sessionmaker, await _user(sessionmaker), clock)
    created = await _last_used(sessionmaker, issued.session_id)
    clock.advance(timedelta(minutes=1))
    await _resolve(sessionmaker, issued.token, clock)
    assert await _last_used(sessionmaker, issued.session_id) == created
    clock.advance(timedelta(minutes=5))
    await _resolve(sessionmaker, issued.token, clock)
    assert await _last_used(sessionmaker, issued.session_id) == T0 + timedelta(minutes=6)


async def test_suspended_user_session_rejected(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    for status in ("suspended", "banned", "deleted"):
        issued = await _session(sessionmaker, await _user(sessionmaker, status), clock)
        response = await client.get("/v1/me/sessions", headers=_headers(issued.token))
        assert response.status_code == 401


async def test_rotate_invalidates_old_token(
    sessionmaker: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    user_id = await _user(sessionmaker)
    old = await _session(sessionmaker, user_id, clock)
    async with sessionmaker() as db:
        current = await resolve_session(db, old.token, policy=POLICY, clock=clock)
        assert current is not None
        new = await rotate_session(db, current=current, strong=True, policy=POLICY, clock=clock)
        await db.commit()
    assert new.token != old.token
    assert await _resolve(sessionmaker, old.token, clock) is None
    rotated = await _resolve(sessionmaker, new.token, clock)
    assert rotated is not None and rotated.mfa_at == T0


# --- HTTP --------------------------------------------------------------------------------


async def test_anonymous_gets_401(client: AsyncClient) -> None:
    response = await client.get("/v1/me/sessions")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    unknown = await client.get("/v1/me/sessions", headers=_headers("forged-token"))
    assert unknown.status_code == 401


async def test_sessions_list_shape(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    user_id = await _user(sessionmaker)
    current = await _session(sessionmaker, user_id, clock)
    other = await _session(sessionmaker, user_id, clock)
    response = await client.get("/v1/me/sessions", headers=_headers(current.token))
    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()["data"]}
    assert set(rows) == {str(current.session_id), str(other.session_id)}
    assert rows[str(current.session_id)]["current"] is True
    assert rows[str(other.session_id)]["current"] is False
    first = rows[str(current.session_id)]
    assert first["device_label"] == "Chrome · macOS"
    assert first["country_code"] == "FR"
    assert "ip" not in first and "user_agent" not in first


async def test_revoked_session_rejected_next_request(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    user_id = await _user(sessionmaker)
    laptop = await _session(sessionmaker, user_id, clock)
    phone = await _session(sessionmaker, user_id, clock)
    assert (await client.get("/v1/me/sessions", headers=_headers(phone.token))).status_code == 200
    revoked = await client.delete(
        f"/v1/me/sessions/{phone.session_id}", headers=_headers(laptop.token, unsafe=True)
    )
    assert revoked.status_code == 204
    assert (await client.get("/v1/me/sessions", headers=_headers(phone.token))).status_code == 401


async def test_delete_other_users_session_404(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    mine = await _session(sessionmaker, await _user(sessionmaker), clock)
    theirs = await _session(sessionmaker, await _user(sessionmaker), clock)
    response = await client.delete(
        f"/v1/me/sessions/{theirs.session_id}", headers=_headers(mine.token, unsafe=True)
    )
    assert response.status_code == 404
    assert await _resolve(sessionmaker, theirs.token, clock) is not None


async def test_revoke_all_keeps_current(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    user_id = await _user(sessionmaker)
    current = await _session(sessionmaker, user_id, clock)
    others = [await _session(sessionmaker, user_id, clock) for _ in range(2)]
    response = await client.delete("/v1/me/sessions", headers=_headers(current.token, unsafe=True))
    assert response.status_code == 204
    assert await _resolve(sessionmaker, current.token, clock) is not None
    for other in others:
        assert await _resolve(sessionmaker, other.token, clock) is None


async def test_logout_revokes_and_clears_cookie(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    issued = await _session(sessionmaker, await _user(sessionmaker), clock)
    response = await client.post("/v1/auth/logout", headers=_headers(issued.token, unsafe=True))
    assert response.status_code == 204
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f"{SESSION_COOKIE}=") and "Max-Age=0" in cleared
    assert await _resolve(sessionmaker, issued.token, clock) is None


async def test_user_rate_limit_per_minute(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> None:
    issued = await _session(sessionmaker, await _user(sessionmaker), clock)
    async with _client(sessionmaker, redis_client, clock, rate_limit_user_per_minute=3) as c:
        statuses = [
            (await c.get("/v1/me/sessions", headers=_headers(issued.token))).status_code
            for _ in range(4)
        ]
    assert statuses == [200, 200, 200, 429]
