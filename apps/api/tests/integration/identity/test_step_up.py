"""Step-up: confirm a recent strong sign-in with a passkey or an e-mailed link (P1-T04b, 13.2)."""

import re
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, TEST_SECRET, make_settings
from tests.integration.identity.test_passkeys import (
    T0,
    WEB,
    Member,
    make_member,
    passkey_app,
    register_passkey,
)
from trovelya.core.csrf import CSRF_COOKIE, SESSION_COOKIE, issue_csrf_token
from trovelya.core.email import open_email
from trovelya.shared.clock import FixedClock

STEP_UP = "/v1/auth/step-up"


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
    app = passkey_app(sessionmaker, redis_client, clock)
    app.state.queue = queue
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


def _token_of(response: Response) -> str:
    for cookie in response.headers.get_list("set-cookie"):
        if cookie.startswith(f"{SESSION_COOKIE}="):
            return cookie.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError("no session cookie")


def _as(token: str) -> dict[str, str]:
    csrf = issue_csrf_token(TEST_SECRET)
    return {"cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}", "x-csrf-token": csrf}


async def _passkey_id(client: AsyncClient, headers: dict[str, str]) -> str:
    [passkey] = (await client.get("/v1/me/passkeys", headers=headers)).json()["data"]
    return passkey["id"]


async def _stale_member_with_passkey(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> tuple[Member, Any]:
    member = await make_member(sessionmaker, clock)
    authenticator = member.authenticator()
    assert (await register_passkey(client, member, authenticator)).status_code == 201
    clock.advance(timedelta(hours=13))  # the strong sign-in is now too old
    client.cookies.clear()
    return member, authenticator


async def test_step_up_with_passkey_rotates_session(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member, authenticator = await _stale_member_with_passkey(sessionmaker, client, clock)
    passkey_id = await _passkey_id(client, member.headers)
    assert (
        await client.delete(f"/v1/me/passkeys/{passkey_id}", headers=member.headers)
    ).status_code == 403

    options = await client.post(f"{STEP_UP}/options", headers=member.headers)
    assert options.status_code == 200
    assert [c["id"] for c in options.json()["allowCredentials"]] == [authenticator.id]
    response = await client.post(
        STEP_UP,
        headers=member.headers,
        json={"method": "passkey", "credential": authenticator.assert_(options.json())},
    )
    assert response.status_code == 204, response.text
    new_token = _token_of(response)
    client.cookies.clear()

    # The old token is revoked (anti-fixation), the new one carries the fresh proof.
    assert (await client.get("/v1/me/passkeys", headers=member.headers)).status_code == 401
    assert (
        await client.delete(f"/v1/me/passkeys/{passkey_id}", headers=_as(new_token))
    ).status_code == 204


async def test_step_up_refuses_another_users_passkey(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member, _ = await _stale_member_with_passkey(sessionmaker, client, clock)
    other = await make_member(sessionmaker, clock)
    other_key = other.authenticator()
    await register_passkey(client, other, other_key)
    client.cookies.clear()
    options = (await client.post(f"{STEP_UP}/options", headers=member.headers)).json()
    response = await client.post(
        STEP_UP,
        headers=member.headers,
        json={"method": "passkey", "credential": other_key.assert_(options)},
    )
    assert response.status_code == 400 and response.json()["code"] == "passkey_invalid"


async def test_login_challenge_cannot_serve_a_step_up(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member, authenticator = await _stale_member_with_passkey(sessionmaker, client, clock)
    login_options = (await client.post("/v1/auth/passkeys/login/options")).json()
    response = await client.post(
        STEP_UP,
        headers=member.headers,
        json={"method": "passkey", "credential": authenticator.assert_(login_options)},
    )
    assert response.status_code == 400


async def test_step_up_via_magic_link(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    member, _ = await _stale_member_with_passkey(sessionmaker, client, clock)
    requested = await client.post(STEP_UP, headers=member.headers, json={"method": "magic_link"})
    assert requested.status_code == 202
    [(_, (sealed,))] = queue.jobs
    message = open_email(sealed, settings=make_settings(web_origin=WEB))
    assert message.to == f"{member.id.hex}@example.org"
    found = re.search(rf"{WEB}/fr/confirmer#token=([A-Za-z0-9_-]+)", message.text)
    assert found is not None

    verified = await client.post(
        f"{STEP_UP}/verify", headers=member.headers, json={"token": found.group(1)}
    )
    assert verified.status_code == 204
    passkey_id = await _passkey_id(client, _as(_token_of(verified)))
    client.cookies.clear()
    assert (
        await client.delete(f"/v1/me/passkeys/{passkey_id}", headers=_as(_token_of(verified)))
    ).status_code == 204


async def test_step_up_link_bound_to_its_account_and_single_use(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    member = await make_member(sessionmaker, clock)
    other = await make_member(sessionmaker, clock)
    await client.post(STEP_UP, headers=member.headers, json={"method": "magic_link"})
    message = open_email(queue.jobs[-1][1][0], settings=make_settings(web_origin=WEB))
    token = message.text.split("#token=", 1)[1].split()[0]
    client.cookies.clear()
    stolen = await client.post(f"{STEP_UP}/verify", headers=other.headers, json={"token": token})
    assert stolen.status_code == 400 and stolen.json()["code"] == "magic_link_invalid"
    # The refused attempt rolls back: another account cannot burn the owner's link.
    client.cookies.clear()
    used = await client.post(f"{STEP_UP}/verify", headers=member.headers, json={"token": token})
    assert used.status_code == 204
    # Single use, even from the owner's new session.
    client.cookies.clear()
    again = await client.post(
        f"{STEP_UP}/verify", headers=_as(_token_of(used)), json={"token": token}
    )
    assert again.status_code == 400


async def test_sign_in_link_cannot_serve_a_step_up(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    member = await make_member(sessionmaker, clock)
    email = await _email_of(sessionmaker, member)
    client.cookies.clear()
    await client.post("/v1/auth/magic-link", json={"email": email})
    message = open_email(queue.jobs[-1][1][0], settings=make_settings(web_origin=WEB))
    token = message.text.split("#token=", 1)[1].split()[0]
    response = await client.post(f"{STEP_UP}/verify", headers=member.headers, json={"token": token})
    assert response.status_code == 400


async def test_step_up_requires_a_session(client: AsyncClient) -> None:
    assert (await client.post(STEP_UP, json={"method": "magic_link"})).status_code == 401
    assert (await client.post(f"{STEP_UP}/verify", json={"token": "x"})).status_code == 401


async def test_passkey_method_needs_a_credential(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    member = await make_member(sessionmaker, clock)
    response = await client.post(STEP_UP, headers=member.headers, json={"method": "passkey"})
    assert response.status_code == 422


async def _email_of(sessionmaker: async_sessionmaker[AsyncSession], member: Member) -> str:
    async with sessionmaker() as db:
        email: str = await db.scalar(
            text("SELECT email FROM users WHERE id = :id"), {"id": member.id}
        )
    return email
