"""Changing the account's e-mail address (P1-T05c, section 13.2)."""

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
from trovelya.core.email import open_email
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

WEB = "https://web.example.test"
SETTINGS = make_settings(web_origin=WEB)


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))

    def messages(self) -> list[Any]:
        return [open_email(args[0], settings=SETTINGS) for _, args in self.jobs]


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


def _new_address() -> str:
    return f"new_{new_id().hex}@example.org"


def _token(message: Any) -> str:
    found = re.search(rf"{WEB}/fr/compte/email/confirmer#token=([A-Za-z0-9_.-]+)", message.text)
    assert found is not None
    return found.group(1)


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


async def test_change_email_flow_emits_event(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    account = await make_account(sessionmaker, completed=True)
    new = _new_address()
    requested = await client.post("/v1/me/email", headers=account.headers, json={"new_email": new})
    assert requested.status_code == 202
    [link_message] = queue.messages()
    assert link_message.to == new
    token = _token(link_message)

    # The link works without a session: it may be opened on another device.
    client.cookies.clear()
    verified = await client.post("/v1/auth/email-change/verify", json={"token": token})
    assert verified.status_code == 204, verified.text
    assert (
        await _scalar(sessionmaker, "SELECT email::text FROM users WHERE id = :id", id=account.id)
        == new
    )
    events = await _scalar(
        sessionmaker,
        "SELECT count(*) FROM outbox_events"
        " WHERE aggregate_id = :id AND type = 'user.email_changed'",
        id=account.id,
    )
    assert events == 1
    # The old address is told, without any link that would undo it.
    notice = queue.messages()[-1]
    assert notice.to == account.email
    assert "#token=" not in notice.text and new not in notice.text
    # Single use.
    again = await client.post("/v1/auth/email-change/verify", json={"token": token})
    assert again.status_code == 400 and again.json()["code"] == "magic_link_invalid"


async def test_change_email_requires_step_up(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    account = await make_account(sessionmaker, completed=True)
    clock.advance(timedelta(hours=13))
    response = await client.post(
        "/v1/me/email", headers=account.headers, json={"new_email": _new_address()}
    )
    assert response.status_code == 403 and response.json()["code"] == "step_up_required"
    assert queue.jobs == []


async def test_taken_address_answers_the_same_and_sends_nothing(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    other = await make_account(sessionmaker, completed=True)
    account = await make_account(sessionmaker, completed=True)
    for address in (other.email, account.email.upper()):
        response = await client.post(
            "/v1/me/email", headers=account.headers, json={"new_email": address}
        )
        assert response.status_code == 202
    assert queue.jobs == []


async def test_tampered_or_foreign_tokens_refused(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    account = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    await client.post("/v1/me/email", headers=account.headers, json={"new_email": _new_address()})
    token = _token(queue.messages()[-1])
    _, secret = token.split(".", 1)
    client.cookies.clear()
    for forged in (f"{other.id.hex}.{secret}", secret, "not-a-token", f"{account.id.hex}.x"):
        response = await client.post("/v1/auth/email-change/verify", json={"token": forged})
        assert response.status_code == 400, forged
    # The genuine token still works after the failed attempts.
    assert (
        await client.post("/v1/auth/email-change/verify", json={"token": token})
    ).status_code == 204


async def test_address_taken_meanwhile(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    account = await make_account(sessionmaker, completed=True)
    new = _new_address()
    await client.post("/v1/me/email", headers=account.headers, json={"new_email": new})
    token = _token(queue.messages()[-1])
    await make_account(sessionmaker, email=new, completed=True)
    client.cookies.clear()
    response = await client.post("/v1/auth/email-change/verify", json={"token": token})
    assert response.status_code == 409 and response.json()["code"] == "email_taken"


async def test_invalid_address_422(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker, completed=True)
    response = await client.post(
        "/v1/me/email", headers=account.headers, json={"new_email": "pas-un-email"}
    )
    assert response.status_code == 422
