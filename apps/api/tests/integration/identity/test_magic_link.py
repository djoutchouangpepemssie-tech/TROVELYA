"""Passwordless sign-in by magic link (P1-T02c part 2, sections 11.4, 11.5 and 13)."""

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from trovelya.core.csrf import SESSION_COOKIE
from trovelya.core.email import open_email
from trovelya.main import create_app
from trovelya.modules.identity.service import purge_expired_magic_links
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
_LINKS_OF = "SELECT count(*) FROM magic_links WHERE email = :e"
WEB = "https://web.example.test"


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


class RejectingCaptcha:
    async def verify(self, token: str | None, *, ip: str) -> bool:
        return False


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
    app = create_app(make_settings(web_origin=WEB))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = clock
    app.state.queue = queue
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


def _email() -> str:
    return f"{new_id().hex}@example.org"


def _ip(n: int = 7) -> dict[str, str]:
    return {"x-trv-client-ip": f"203.0.113.{n}"}


async def _request(client: AsyncClient, email: str, ip: int = 7) -> Response:
    client.cookies.clear()
    return await client.post("/v1/auth/magic-link", json={"email": email}, headers=_ip(ip))


def _last_token(queue: RecordingQueue) -> str:
    message = open_email(queue.jobs[-1][1][0], settings=make_settings(web_origin=WEB))
    found = re.search(r"#token=([A-Za-z0-9_-]+)", message.text)
    assert found is not None
    return found.group(1)


async def _verify(client: AsyncClient, token: str) -> Response:
    # A fresh browser: a session cookie from an earlier sign-in would require a CSRF token.
    client.cookies.clear()
    return await client.post("/v1/auth/magic-link/verify", json={"token": token}, headers=_ip())


async def _user(
    sessionmaker: async_sessionmaker[AsyncSession], email: str, *, staff: bool = False
) -> UUID:
    user_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO users"
                " (id, email, username, display_name, is_staff, profile_completed_at)"
                " VALUES (:id, :email, :username, 'Membre', :staff, now())"
            ),
            {"id": user_id, "email": email, "username": f"u_{user_id.hex[-8:]}", "staff": staff},
        )
        await db.commit()
    return user_id


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


# --- Request -----------------------------------------------------------------------------


async def test_request_same_response_known_and_unknown_email(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    known = _email()
    await _user(sessionmaker, known)
    unknown = _email()
    first, second = await _request(client, known), await _request(client, unknown)
    assert (first.status_code, first.json()) == (second.status_code, second.json()) == (202, {})
    ignored = {"x-request-id", "date"}
    assert {k for k in first.headers if k not in ignored} == {
        k for k in second.headers if k not in ignored
    }
    assert len(queue.jobs) == 2
    for email in (known, unknown):
        count = await _scalar(
            sessionmaker, "SELECT count(*) FROM magic_links WHERE email = :e", e=email
        )
        assert count == 1


@pytest.mark.parametrize("email", ["", "pas-un-email", "a@b", "x" * 250 + "@example.org"])
async def test_invalid_email_422(client: AsyncClient, email: str) -> None:
    assert (await _request(client, email)).status_code == 422


async def test_link_points_to_verify_page_with_fragment(
    client: AsyncClient, queue: RecordingQueue
) -> None:
    email = _email()
    await _request(client, email)
    message = open_email(queue.jobs[-1][1][0], settings=make_settings(web_origin=WEB))
    assert message.to == email
    assert f"{WEB}/fr/verifier#token=" in message.text
    assert message.html is not None and f"{WEB}/fr/verifier#token=" in message.html


async def test_rate_limit_5_per_hour_per_email(client: AsyncClient, redis_client: Redis) -> None:
    email = _email()
    statuses = [(await _request(client, email, ip=n)).status_code for n in range(1, 7)]
    assert statuses == [202] * 5 + [429]
    keys = [key.decode() for key in await redis_client.keys("*")]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert not any(email in key or "203.0.113" in key for key in keys)


async def test_rate_limit_20_per_hour_per_ip(client: AsyncClient) -> None:
    statuses = [(await _request(client, _email(), ip=99)).status_code for _ in range(21)]
    assert statuses == [202] * 20 + [429]


async def test_captcha_required_when_enabled(client: AsyncClient) -> None:
    transport = client._transport  # pyright: ignore[reportPrivateUsage]
    transport.app.state.captcha = RejectingCaptcha()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    response = await _request(client, _email())
    assert response.status_code == 400
    assert response.json()["code"] == "captcha_failed"


# --- Verify ------------------------------------------------------------------------------


async def test_verify_creates_user_once(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    email = _email()
    await _request(client, email)
    response = await _verify(client, _last_token(queue))
    assert response.status_code == 200
    body = response.json()
    assert body["is_new"] is True and body["profile_completed"] is False
    assert response.headers["set-cookie"].startswith(f"{SESSION_COOKIE}=")
    user_id = UUID(body["user_id"])
    assert await _scalar(
        sessionmaker, "SELECT email_verified_at = :t0 FROM users WHERE id = :id", id=user_id, t0=T0
    )
    assert (
        await _scalar(
            sessionmaker, "SELECT count(*) FROM user_preferences WHERE user_id = :id", id=user_id
        )
        == 1
    )
    events = await _scalar(
        sessionmaker,
        "SELECT array_agg(type ORDER BY type) FROM outbox_events WHERE aggregate_id = :id",
        id=user_id,
    )
    assert events == ["session.created", "user.registered"]

    await _request(client, email)
    again = await _verify(client, _last_token(queue))
    assert again.json()["is_new"] is False and again.json()["user_id"] == str(user_id)


async def test_verify_existing_user_not_new(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    email = _email()
    user_id = await _user(sessionmaker, email)
    await _request(client, email)
    body = (await _verify(client, _last_token(queue))).json()
    assert body == {"user_id": str(user_id), "is_new": False, "profile_completed": True}


async def test_magic_link_single_use(client: AsyncClient, queue: RecordingQueue) -> None:
    await _request(client, _email())
    token = _last_token(queue)
    assert (await _verify(client, token)).status_code == 200
    second = await _verify(client, token)
    assert second.status_code == 400 and second.json()["code"] == "magic_link_invalid"


async def test_magic_link_expires_15_min(
    client: AsyncClient, queue: RecordingQueue, clock: FixedClock
) -> None:
    await _request(client, _email())
    clock.advance(timedelta(minutes=15, seconds=1))
    assert (await _verify(client, _last_token(queue))).status_code == 400


async def test_unknown_token_400(client: AsyncClient) -> None:
    response = await _verify(client, "forged-token")
    assert response.status_code == 400 and response.json()["code"] == "magic_link_invalid"


async def test_magic_link_concurrent_verify_single_session(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    email = _email()
    await _request(client, email)
    token = _last_token(queue)
    first, second = await asyncio.gather(_verify(client, token), _verify(client, token))
    assert sorted([first.status_code, second.status_code]) == [200, 400]
    sessions = await _scalar(
        sessionmaker,
        "SELECT count(*) FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.email = :e",
        e=email,
    )
    assert sessions == 1


async def test_staff_email_cannot_use_magic_link(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    email = _email()
    staff_id = await _user(sessionmaker, email, staff=True)
    assert (await _request(client, email)).status_code == 202
    response = await _verify(client, _last_token(queue))
    assert response.status_code == 400 and response.json()["code"] == "magic_link_invalid"
    assert (
        await _scalar(
            sessionmaker, "SELECT count(*) FROM sessions WHERE user_id = :id", id=staff_id
        )
        == 0
    )


async def test_token_never_logged(
    client: AsyncClient, queue: RecordingQueue, capsys: pytest.CaptureFixture[str]
) -> None:
    email = _email()
    await _request(client, email)
    token = _last_token(queue)
    await _verify(client, token)
    output = capsys.readouterr().out
    for secret in (email, token, "203.0.113.7"):
        assert secret not in output


async def test_purge_expired_links(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    email = _email()
    await _request(client, email)
    clock.advance(timedelta(hours=24, minutes=16))
    purged = await purge_expired_magic_links(sessionmaker, clock=clock)
    assert purged >= 1
    assert (
        await _scalar(sessionmaker, "SELECT count(*) FROM magic_links WHERE email = :e", e=email)
        == 0
    )
