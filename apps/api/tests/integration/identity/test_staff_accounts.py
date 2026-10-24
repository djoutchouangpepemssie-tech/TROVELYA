"""Staff accounts: creation by script and passkey enrolment link (P1-T11b, ADR-0018, Q18)."""

import re
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.fake_webauthn import SoftAuthenticator
from tests.integration.identity.test_profile import T0, make_account
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.identity.service.staff_accounts import (
    StaffAccountError,
    issue_staff_enrolment,
)
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

WEB = "https://web.example.test"
RP_ID = "web.example.test"
SETTINGS = make_settings(web_origin=WEB)
ROLE = "staff_superadmin"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


def _app(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    clock: FixedClock,
    *,
    passkeys: bool,
) -> Any:
    app = create_app(SETTINGS)
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = clock
    app.state.flags = FlagService(sessionmaker, redis_client, {"auth.passkeys": passkeys})
    return app


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> AsyncIterator[AsyncClient]:
    app = _app(sessionmaker, redis_client, clock, passkeys=True)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


def _email() -> str:
    return f"arcel+staff_{new_id().hex[-10:]}@example.org"


def _token(link: str) -> str:
    found = re.fullmatch(rf"{WEB}/fr/staff/enrolement#token=([A-Za-z0-9_-]+)", link)
    assert found is not None, link
    return found.group(1)


async def _create(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    clock: FixedClock,
    email: str,
    role: str = ROLE,
) -> tuple[UUID, str]:
    enrolment = await issue_staff_enrolment(
        sessionmaker, redis_client, email=email, role=role, settings=SETTINGS, clock=clock
    )
    return enrolment.user_id, _token(enrolment.link)


async def _enrol(
    client: AsyncClient, token: str, user_id: UUID
) -> tuple[Response, SoftAuthenticator]:
    client.cookies.clear()
    options = await client.post("/v1/auth/passkeys/enrol/options", json={"enrolment_token": token})
    assert options.status_code == 200, options.text
    authenticator = SoftAuthenticator(rp_id=RP_ID, origin=WEB, user_handle=user_id.bytes)
    credential = authenticator.register(options.json())
    verified = await client.post(
        "/v1/auth/passkeys/enrol/verify",
        json={"enrolment_token": token, "credential": credential, "name": "Passkey staff"},
    )
    return verified, authenticator


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


async def test_create_staff_script_enrolment_link_single_use(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    client: AsyncClient,
    clock: FixedClock,
) -> None:
    email = _email()
    user_id, token = await _create(sessionmaker, redis_client, clock, email)
    async with sessionmaker() as db:
        account = (
            await db.execute(
                text(
                    "SELECT is_staff, profile_completed_at IS NOT NULL AS completed,"
                    " (SELECT array_agg(role_key) FROM user_roles WHERE user_id = u.id) AS roles"
                    " FROM users u WHERE id = :id"
                ),
                {"id": user_id},
            )
        ).one()
    assert account.is_staff and account.completed and account.roles == [ROLE]

    verified, authenticator = await _enrol(client, token, user_id)
    assert verified.status_code == 200, verified.text
    assert verified.json()["user_id"] == str(user_id)
    kind = await _scalar(
        sessionmaker,
        "SELECT kind FROM sessions WHERE user_id = :id AND revoked_at IS NULL",
        id=user_id,
    )
    assert kind == "admin"
    # A staff session reaches the back office.
    assert (await client.get("/v1/staff/approvals")).status_code == 200

    # Single use.
    client.cookies.clear()
    again = await client.post("/v1/auth/passkeys/enrol/options", json={"enrolment_token": token})
    assert again.status_code == 400 and again.json()["code"] == "enrolment_invalid"

    # The enrolled passkey signs in to an admin session.
    client.cookies.clear()
    options = (await client.post("/v1/auth/passkeys/login/options")).json()
    login = await client.post(
        "/v1/auth/passkeys/login/verify", json={"credential": authenticator.assert_(options)}
    )
    assert login.status_code == 200


async def test_enrolment_token_single_use_and_expires(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    client: AsyncClient,
    clock: FixedClock,
) -> None:
    user_id, token = await _create(sessionmaker, redis_client, clock, _email())
    clock.advance(timedelta(minutes=15, seconds=1))
    expired = await client.post("/v1/auth/passkeys/enrol/options", json={"enrolment_token": token})
    assert expired.status_code == 400 and expired.json()["code"] == "enrolment_invalid"
    for bogus in ("", "x" * 200, "pas-un-jeton"):
        response = await client.post(
            "/v1/auth/passkeys/enrol/options", json={"enrolment_token": bogus}
        )
        assert response.status_code in (400, 422)
    assert (
        await _scalar(sessionmaker, "SELECT count(*) FROM passkeys WHERE user_id = :id", id=user_id)
        == 0
    )


async def test_failed_verification_keeps_the_link(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    client: AsyncClient,
    clock: FixedClock,
) -> None:
    """A wrong origin (phishing page) is refused and the genuine link still works."""
    user_id, token = await _create(sessionmaker, redis_client, clock, _email())
    options = (
        await client.post("/v1/auth/passkeys/enrol/options", json={"enrolment_token": token})
    ).json()
    phishing = SoftAuthenticator(
        rp_id=RP_ID, origin="https://evil.example", user_handle=user_id.bytes
    )
    refused = await client.post(
        "/v1/auth/passkeys/enrol/verify",
        json={"enrolment_token": token, "credential": phishing.register(options)},
    )
    assert refused.status_code == 400
    verified, _ = await _enrol(client, token, user_id)
    assert verified.status_code == 200, verified.text


async def test_create_staff_refuses_client_email(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> None:
    member = await make_account(sessionmaker, completed=True)
    with pytest.raises(StaffAccountError, match="client"):
        await _create(sessionmaker, redis_client, clock, member.email.upper())
    is_staff = await _scalar(
        sessionmaker, "SELECT is_staff FROM users WHERE id = :id", id=member.id
    )
    assert is_staff is False


async def test_create_staff_refuses_unknown_or_non_staff_role(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> None:
    for role in ("member", "staff_inconnu"):
        with pytest.raises(StaffAccountError, match="rôle"):
            await _create(sessionmaker, redis_client, clock, _email(), role=role)


async def test_new_link_for_a_staff_account_without_passkey_only(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    client: AsyncClient,
    clock: FixedClock,
) -> None:
    email = _email()
    user_id, first = await _create(sessionmaker, redis_client, clock, email)
    again_id, second = await _create(sessionmaker, redis_client, clock, email)
    assert again_id == user_id and second != first
    verified, _ = await _enrol(client, second, user_id)
    assert verified.status_code == 200
    with pytest.raises(StaffAccountError, match="passkey"):
        await _create(sessionmaker, redis_client, clock, email)


async def test_enrolment_works_with_the_passkeys_flag_off(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> None:
    """Staff must be able to enrol before passkeys are opened to members."""
    user_id, token = await _create(sessionmaker, redis_client, clock, _email())
    app = _app(sessionmaker, redis_client, clock, passkeys=False)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as off:
        off.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        verified, authenticator = await _enrol(off, token, user_id)
        assert verified.status_code == 200, verified.text
        # Staff sign-in by passkey stays open too; members' passkey routes stay hidden.
        off.cookies.clear()
        options = await off.post("/v1/auth/passkeys/login/options")
        assert options.status_code == 200
        login = await off.post(
            "/v1/auth/passkeys/login/verify",
            json={"credential": authenticator.assert_(options.json())},
        )
        assert login.status_code == 200
        off.cookies.clear()
        assert (await off.post("/v1/auth/passkeys/register/options")).status_code == 404


async def test_staff_creation_and_enrolment_audited(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    client: AsyncClient,
    clock: FixedClock,
) -> None:
    user_id, token = await _create(sessionmaker, redis_client, clock, _email())
    await _enrol(client, token, user_id)
    async with sessionmaker() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT action, actor_type FROM audit_log WHERE target_type = 'user'"
                    " AND target_id = :id ORDER BY id"
                ),
                {"id": str(user_id)},
            )
        ).all()
    assert [(r.action, r.actor_type) for r in rows] == [
        ("staff.create", "system"),
        ("staff.enrolment_link", "system"),
        ("staff.passkey_enrolled", "staff"),
    ]


def test_create_staff_command_prints_the_link_once(
    migrated_url: str,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from trovelya.scripts import create_staff

    settings = make_settings(web_origin=WEB, database_url=migrated_url, redis_url=redis_url)
    monkeypatch.setattr(create_staff, "get_settings", lambda: settings)
    email = _email()
    assert create_staff.main(["--email", email, "--role", ROLE]) == 0
    out = capsys.readouterr().out
    assert "Compte staff créé" in out
    assert re.search(rf"{WEB}/fr/staff/enrolement#token=[A-Za-z0-9_-]+", out)

    # A customer address is refused with a readable message.
    assert (
        create_staff.main(["--email", email.replace("+staff", "+client"), "--role", "member"]) == 1
    )
    assert "Refusé" in capsys.readouterr().err
