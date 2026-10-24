"""Profile completion, `GET /v1/me` and the completed-profile rule (P1-T05a, Q11, E14)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, TEST_SECRET, make_settings
from trovelya.core.csrf import CSRF_COOKIE, SESSION_COOKIE, issue_csrf_token
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.identity.service import SessionPolicy, create_session
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
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings())
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = FixedClock(T0)
    app.state.flags = FlagService(sessionmaker, redis_client, {"auth.passkeys": True})
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


class Account:
    def __init__(self, user_id: UUID, email: str, token: str) -> None:
        self.id = user_id
        self.email = email
        csrf = issue_csrf_token(TEST_SECRET)
        self.headers = {
            "cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}",
            "x-csrf-token": csrf,
        }


async def make_account(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email: str | None = None,
    username: str | None = None,
    completed: bool = False,
) -> Account:
    user_id = new_id()
    email = email or f"{user_id.hex}@example.org"
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, username, display_name, email_verified_at,"
                " profile_completed_at, birth_year)"
                " VALUES (:id, :email, :u, 'Membre', now(),"
                " CASE WHEN :done THEN now() END, CASE WHEN :done THEN 1990 END)"
            ),
            {
                "id": user_id,
                "email": email,
                "u": username or f"membre_{user_id.hex[-8:]}",
                "done": completed,
            },
        )
        await db.execute(
            text("INSERT INTO user_preferences (user_id) VALUES (:id)"), {"id": user_id}
        )
        issued = await create_session(
            db,
            user_id=user_id,
            kind="web",
            ip="203.0.113.7",
            user_agent=None,
            country="FR",
            strong=True,
            policy=POLICY,
            clock=FixedClock(T0),
        )
        await db.commit()
    return Account(user_id, email, issued.token)


def profile_form(**overrides: Any) -> dict[str, Any]:
    form: dict[str, Any] = {
        "username": f"user_{new_id().hex[-8:]}",
        "display_name": "Arcel D.",
        "birth_year": 1990,
        "accept_terms": True,
        "terms_version": "2026-10",
    }
    form.update(overrides)
    return form


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


async def test_me_before_completion(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    me = (await client.get("/v1/me", headers=account.headers)).json()
    assert me["id"] == str(account.id) and me["email"] == account.email
    assert me["profile_completed"] is False and me["is_minor"] is None
    assert me["counters"] == {"unread_messages": 0, "notifications": 0}
    assert me["roles"] == [] and me["flags"]["auth.passkeys"] is True
    assert me["version"] >= 1


async def test_complete_profile_ok(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    form = profile_form()
    response = await client.post("/v1/me/complete-profile", headers=account.headers, json=form)
    assert response.status_code == 200, response.text
    me = response.json()
    assert me["profile_completed"] is True and me["username"] == form["username"]
    assert me["display_name"] == "Arcel D." and me["is_minor"] is False
    consent = await _scalar(
        sessionmaker,
        "SELECT policy_version || ':' || granted::text || ':' || source FROM consents"
        " WHERE user_id = :id AND purpose = 'terms'",
        id=account.id,
    )
    assert consent == "2026-10:true:signup"
    again = await client.post(
        "/v1/me/complete-profile", headers=account.headers, json=profile_form()
    )
    assert again.status_code == 409 and again.json()["code"] == "profile_already_completed"


async def test_terms_must_be_accepted(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    response = await client.post(
        "/v1/me/complete-profile", headers=account.headers, json=profile_form(accept_terms=False)
    )
    assert response.status_code == 422


async def test_too_young_rejected_and_nothing_kept(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO magic_links (id, email, token_hash, purpose, expires_at, created_at)"
                " VALUES (:id, :email, :hash, 'login', now(), now())"
            ),
            {"id": new_id(), "email": account.email, "hash": new_id().bytes},
        )
        await db.commit()
    response = await client.post(
        "/v1/me/complete-profile", headers=account.headers, json=profile_form(birth_year=2012)
    )
    assert response.status_code == 400 and response.json()["code"] == "too_young"
    assert any(
        c.startswith(f'{SESSION_COOKIE}=""') or c.startswith(f"{SESSION_COOKIE}=;")
        for c in response.headers.get_list("set-cookie")
    )
    for sql in (
        "SELECT count(*) FROM users WHERE id = :id",
        "SELECT count(*) FROM sessions WHERE user_id = :id",
        "SELECT count(*) FROM user_preferences WHERE user_id = :id",
        "SELECT count(*) FROM consents WHERE user_id = :id",
    ):
        assert await _scalar(sessionmaker, sql, id=account.id) == 0, sql
    assert (
        await _scalar(
            sessionmaker, "SELECT count(*) FROM magic_links WHERE email = :e", e=account.email
        )
        == 0
    )
    assert (await client.get("/v1/me", headers=account.headers)).status_code == 401


@pytest.mark.parametrize(
    ("birth_year", "accepted", "minor"),
    [(2010, True, True), (2011, False, None), (2007, True, False), (2008, True, True)],
)
async def test_age_rule_b(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    birth_year: int,
    accepted: bool,
    minor: bool | None,
) -> None:
    """In 2026: age = 2026 - year - 1. Sign-up from 15, adult from 18 (E14, rule B)."""
    account = await make_account(sessionmaker)
    response = await client.post(
        "/v1/me/complete-profile", headers=account.headers, json=profile_form(birth_year=birth_year)
    )
    assert (response.status_code == 200) is accepted
    if accepted:
        assert response.json()["is_minor"] is minor


async def test_birth_year_bounds(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    for year in (1899, 2027):
        response = await client.post(
            "/v1/me/complete-profile", headers=account.headers, json=profile_form(birth_year=year)
        )
        assert response.status_code == 422


async def test_username_case_insensitive(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    taken = f"alice_{new_id().hex[-6:]}"
    await make_account(sessionmaker, username=taken, completed=True)
    account = await make_account(sessionmaker)
    response = await client.post(
        "/v1/me/complete-profile",
        headers=account.headers,
        json=profile_form(username=taken.upper()),
    )
    assert response.status_code == 409 and response.json()["code"] == "username_taken"


async def test_complete_profile_username_race(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    first, second = await make_account(sessionmaker), await make_account(sessionmaker)
    wanted = f"race_{new_id().hex[-8:]}"
    responses = await asyncio.gather(
        *(
            client.post(
                "/v1/me/complete-profile", headers=a.headers, json=profile_form(username=wanted)
            )
            for a in (first, second)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 409]


async def test_username_suggestion(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    local = f"Jean.Dupont+{new_id().hex[-6:]}"
    account = await make_account(sessionmaker, email=f"{local}@example.org")
    expected = local.lower().replace("+", "_")
    suggestion = (await client.get("/v1/me/username-suggestion", headers=account.headers)).json()
    assert suggestion == {"username": expected}
    await make_account(sessionmaker, username=expected, completed=True)
    suggestion = (await client.get("/v1/me/username-suggestion", headers=account.headers)).json()
    assert suggestion == {"username": f"{expected}1"}


async def test_incomplete_profile_blocks_private_routes(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    blocked = await client.get("/v1/me/passkeys", headers=account.headers)
    assert blocked.status_code == 403 and blocked.json()["code"] == "profile_incomplete"
    assert (
        await client.post(
            "/v1/auth/step-up", headers=account.headers, json={"method": "magic_link"}
        )
    ).status_code == 403
    # Still allowed: the account itself, its sessions, sign-out.
    assert (await client.get("/v1/me", headers=account.headers)).status_code == 200
    assert (await client.get("/v1/me/sessions", headers=account.headers)).status_code == 200
    assert (await client.post("/v1/auth/logout", headers=account.headers)).status_code == 204


async def test_birth_year_not_in_logs(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    account = await make_account(sessionmaker)
    await client.post(
        "/v1/me/complete-profile", headers=account.headers, json=profile_form(birth_year=1977)
    )
    await client.post(
        "/v1/me/complete-profile", headers=account.headers, json=profile_form(birth_year=2013)
    )
    assert "1977" not in capsys.readouterr().out
