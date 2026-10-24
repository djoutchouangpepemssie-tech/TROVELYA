"""Passkeys (WebAuthn) and the recent strong sign-in rule (P1-T04, section 13.2)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, TEST_SECRET, make_settings
from tests.fake_webauthn import SoftAuthenticator
from trovelya.core.csrf import CSRF_COOKIE, SESSION_COOKIE, issue_csrf_token
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.identity.service import SessionPolicy, create_session
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
WEB = "https://web.example.test"
RP_ID = "web.example.test"
POLICY = SessionPolicy(
    web_ttl=timedelta(days=30),
    admin_ttl=timedelta(hours=12),
    idle=timedelta(days=14),
    touch_interval=timedelta(minutes=5),
)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


def passkey_app(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    clock: FixedClock,
    *,
    enabled: bool = True,
) -> Any:
    app = create_app(make_settings(web_origin=WEB))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = clock
    app.state.flags = FlagService(sessionmaker, redis_client, {"auth.passkeys": enabled})
    return app


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> AsyncIterator[AsyncClient]:
    app = passkey_app(sessionmaker, redis_client, clock)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


class Member:
    """A signed-in user, with the cookies and CSRF header of their browser."""

    def __init__(self, user_id: UUID, token: str) -> None:
        self.id = user_id
        csrf = issue_csrf_token(TEST_SECRET)
        self.headers = {
            "cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}",
            "x-csrf-token": csrf,
        }

    def authenticator(self, *, origin: str = WEB) -> SoftAuthenticator:
        return SoftAuthenticator(rp_id=RP_ID, origin=origin, user_handle=self.id.bytes)


async def make_member(
    sessionmaker: async_sessionmaker[AsyncSession],
    clock: FixedClock,
    *,
    staff: bool = False,
    status: str = "active",
) -> Member:
    user_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, username, display_name, is_staff, status,"
                " email_verified_at, profile_completed_at)"
                " VALUES (:id, :email, :u, 'Membre', :staff, CAST(:status AS user_status),"
                " now(), now())"
            ),
            {
                "id": user_id,
                "email": f"{user_id.hex}@example.org",
                "u": f"u_{user_id.hex[-8:]}",
                "staff": staff,
                "status": status,
            },
        )
        issued = await create_session(
            db,
            user_id=user_id,
            kind="admin" if staff else "web",
            ip="203.0.113.7",
            user_agent=None,
            country="FR",
            strong=True,
            policy=POLICY,
            clock=clock,
        )
        await db.commit()
    return Member(user_id, issued.token)


async def register_passkey(
    client: AsyncClient, member: Member, authenticator: SoftAuthenticator, **kwargs: Any
) -> Response:
    options = await client.post("/v1/auth/passkeys/register/options", headers=member.headers)
    assert options.status_code == 200, options.text
    credential = authenticator.register(options.json(), **kwargs)
    return await client.post(
        "/v1/auth/passkeys/register/verify",
        headers=member.headers,
        json={"credential": credential, "name": "Mon téléphone"},
    )


async def _login(client: AsyncClient, authenticator: SoftAuthenticator, **kwargs: Any) -> Response:
    client.cookies.clear()
    options = await client.post("/v1/auth/passkeys/login/options")
    assert options.status_code == 200, options.text
    assert options.json()["userVerification"] == "required"
    assert options.json().get("allowCredentials", []) == []  # discoverable credentials
    credential = authenticator.assert_(options.json(), **kwargs)
    return await client.post("/v1/auth/passkeys/login/verify", json={"credential": credential})


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


def _session_cookie(response: Response) -> str | None:
    for cookie in response.headers.get_list("set-cookie"):
        if cookie.startswith(f"{SESSION_COOKIE}="):
            return cookie
    return None


# --- Registration and sign-in --------------------------------------------------------------


async def test_register_and_login(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    authenticator = member.authenticator()
    registered = await register_passkey(client, member, authenticator)
    assert registered.status_code == 201, registered.text
    assert registered.json()["name"] == "Mon téléphone"

    response = await _login(client, authenticator)
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == str(member.id)
    assert _session_cookie(response) is not None
    kinds = await _scalar(
        sessionmaker,
        "SELECT array_agg(kind::text || ':' || (mfa_at IS NOT NULL)::text ORDER BY created_at)"
        " FROM sessions WHERE user_id = :id",
        id=member.id,
    )
    assert kinds[-1] == "web:true"  # a passkey is a strong sign-in
    assert (
        await _scalar(
            sessionmaker, "SELECT sign_count FROM passkeys WHERE user_id = :id", id=member.id
        )
        == 1
    )


async def test_challenge_single_use(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    authenticator = member.authenticator()
    await register_passkey(client, member, authenticator)
    client.cookies.clear()
    options = (await client.post("/v1/auth/passkeys/login/options")).json()
    # Two valid assertions (the counter moves forward) answering the same challenge.
    for expected in (200, 400):
        client.cookies.clear()  # the first sign-in set a session cookie
        response = await client.post(
            "/v1/auth/passkeys/login/verify",
            json={"credential": authenticator.assert_(options)},
        )
        assert response.status_code == expected


async def test_challenge_expires(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    authenticator = member.authenticator()
    options = await client.post("/v1/auth/passkeys/register/options", headers=member.headers)
    clock.advance(timedelta(minutes=5, seconds=1))
    response = await client.post(
        "/v1/auth/passkeys/register/verify",
        headers=member.headers,
        json={"credential": authenticator.register(options.json()), "name": "Clé"},
    )
    assert response.status_code == 400 and response.json()["code"] == "passkey_invalid"


async def test_wrong_origin_rejected(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    response = await register_passkey(
        client, member, member.authenticator(), origin="https://evil.example.test"
    )
    assert response.status_code == 400 and response.json()["code"] == "passkey_invalid"


async def test_wrong_rp_id_rejected(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    response = await register_passkey(
        client, member, member.authenticator(), rp_id="evil.example.test"
    )
    assert response.status_code == 400 and response.json()["code"] == "passkey_invalid"


async def test_sign_count_regression_rejected(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    authenticator = member.authenticator()
    await register_passkey(client, member, authenticator)
    assert (await _login(client, authenticator, sign_count=5)).status_code == 200
    cloned = await _login(client, authenticator, sign_count=3)
    assert cloned.status_code == 400 and cloned.json()["code"] == "passkey_invalid"


async def test_unknown_credential_or_blocked_user_rejected(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    assert (await _login(client, member.authenticator())).status_code == 400

    authenticator = member.authenticator()
    await register_passkey(client, member, authenticator)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE users SET status = 'suspended' WHERE id = :id"), {"id": member.id}
        )
        await db.commit()
    response = await _login(client, authenticator)
    assert response.status_code == 400 and response.json()["code"] == "passkey_invalid"


async def test_user_handle_must_match(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    authenticator = member.authenticator()
    await register_passkey(client, member, authenticator)
    authenticator.user_handle = new_id().bytes
    assert (await _login(client, authenticator)).status_code == 400


async def test_staff_login_gets_admin_session_12h(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    staff = await make_member(sessionmaker, clock, staff=True)
    authenticator = staff.authenticator()
    assert (await register_passkey(client, staff, authenticator)).status_code == 201
    response = await _login(client, authenticator)
    assert response.status_code == 200
    row = await _scalar(
        sessionmaker,
        "SELECT kind::text || ':' || extract(epoch FROM expires_at - created_at)::int::text"
        " FROM sessions WHERE user_id = :id ORDER BY created_at DESC LIMIT 1",
        id=staff.id,
    )
    assert row == f"admin:{12 * 3600}"


# --- Management ----------------------------------------------------------------------------


async def test_multiple_passkeys_list_and_rename(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    for _ in range(2):
        assert (await register_passkey(client, member, member.authenticator())).status_code == 201
    listed = (await client.get("/v1/me/passkeys", headers=member.headers)).json()["data"]
    assert len(listed) == 2
    renamed = await client.patch(
        f"/v1/me/passkeys/{listed[0]['id']}", headers=member.headers, json={"name": "Ordinateur"}
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Ordinateur"


async def test_delete_requires_step_up(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    await register_passkey(client, member, member.authenticator())
    [passkey] = (await client.get("/v1/me/passkeys", headers=member.headers)).json()["data"]

    clock.advance(timedelta(hours=12, seconds=1))  # auth.step_up_max_age_h
    refused = await client.delete(f"/v1/me/passkeys/{passkey['id']}", headers=member.headers)
    assert refused.status_code == 403 and refused.json()["code"] == "step_up_required"
    again = await client.post("/v1/auth/passkeys/register/options", headers=member.headers)
    assert again.status_code == 403


async def test_require_recent_mfa_12h(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    await register_passkey(client, member, member.authenticator())
    [passkey] = (await client.get("/v1/me/passkeys", headers=member.headers)).json()["data"]
    clock.advance(timedelta(hours=11, minutes=59))
    deleted = await client.delete(f"/v1/me/passkeys/{passkey['id']}", headers=member.headers)
    assert deleted.status_code == 204
    assert (await client.get("/v1/me/passkeys", headers=member.headers)).json()["data"] == []


async def test_delete_other_users_passkey_404(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    owner = await make_member(sessionmaker, clock)
    await register_passkey(client, owner, owner.authenticator())
    [passkey] = (await client.get("/v1/me/passkeys", headers=owner.headers)).json()["data"]
    intruder = await make_member(sessionmaker, clock)
    path = f"/v1/me/passkeys/{passkey['id']}"
    assert (await client.delete(path, headers=intruder.headers)).status_code == 404
    assert (
        await client.patch(path, headers=intruder.headers, json={"name": "x"})
    ).status_code == 404


async def test_flag_off_404(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    app = passkey_app(sessionmaker, redis_client, clock, enabled=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        assert (await c.post("/v1/auth/passkeys/login/options")).status_code == 404
        assert (
            await c.post("/v1/auth/passkeys/register/options", headers=member.headers)
        ).status_code == 404
        assert (await c.get("/v1/me/passkeys", headers=member.headers)).status_code == 404
