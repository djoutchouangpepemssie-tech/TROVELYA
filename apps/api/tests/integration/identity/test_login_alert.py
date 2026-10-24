"""New sign-in alert (P1-T02c part 3, section 13.2 E7): new device or new country."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from trovelya.core.db import commit
from trovelya.core.email import open_email
from trovelya.modules.identity.service import identity_subscriptions
from trovelya.shared.events import OutboxEvent
from trovelya.shared.ids import new_id

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
WEB = "https://web.example.test"
SETTINGS = make_settings(web_origin=WEB)
CHROME_MAC = "Chrome · macOS"


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


async def _user(sessionmaker: async_sessionmaker[AsyncSession]) -> UUID:
    user_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, username, display_name)"
                " VALUES (:id, :email, :username, 'Membre')"
            ),
            {
                "id": user_id,
                "email": f"{user_id.hex}@example.org",
                "username": f"u_{user_id.hex[-8:]}",
            },
        )
        await db.commit()
    return user_id


async def _session(
    sessionmaker: async_sessionmaker[AsyncSession],
    user_id: UUID,
    *,
    at: datetime,
    device: str | None = CHROME_MAC,
    country: str | None = "FR",
) -> UUID:
    session_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO sessions (id, user_id, token_hash, kind, created_at, last_used_at,"
                " expires_at, ip, device_label, country_code)"
                " VALUES (:id, :user_id, :hash, 'web', :at, :at, :exp, '203.0.113.7',"
                " :device, :country)"
            ),
            {
                "id": session_id,
                "user_id": user_id,
                "hash": session_id.bytes,
                "at": at,
                "exp": at + timedelta(days=30),
                "device": device,
                "country": country,
            },
        )
        await db.commit()
    return session_id


async def _alert(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: UUID, session_id: UUID
) -> RecordingQueue:
    queue = RecordingQueue()
    (subscription,) = [
        s for s in identity_subscriptions(queue, SETTINGS) if s.event_type == "session.created"
    ]
    event = OutboxEvent(
        id=new_id(),
        type="session.created",
        aggregate_type="user",
        aggregate_id=user_id,
        payload={"session_id": str(session_id)},
        occurred_at=T0,
    )
    async with sessionmaker() as db:
        await subscription.handler(db, event)
        await commit(db)
    return queue


async def test_first_session_sends_no_alert(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user_id = await _user(sessionmaker)
    session_id = await _session(sessionmaker, user_id, at=T0)
    assert (await _alert(sessionmaker, user_id, session_id)).jobs == []


async def test_known_device_and_country_sends_no_alert(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _user(sessionmaker)
    await _session(sessionmaker, user_id, at=T0 - timedelta(days=10))
    session_id = await _session(sessionmaker, user_id, at=T0)
    assert (await _alert(sessionmaker, user_id, session_id)).jobs == []


async def test_new_device_sends_alert_without_ip(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _user(sessionmaker)
    await _session(sessionmaker, user_id, at=T0 - timedelta(days=10))
    session_id = await _session(sessionmaker, user_id, at=T0, device="Firefox · Windows")
    queue = await _alert(sessionmaker, user_id, session_id)
    assert len(queue.jobs) == 1
    message = open_email(queue.jobs[0][1][0], settings=SETTINGS)
    assert message.to == f"{user_id.hex}@example.org"
    assert message.subject == "Nouvelle connexion à votre compte TROVÉLYA"
    assert "Firefox · Windows" in message.text
    assert "24/10/2026 à 14:00" in message.text  # Europe/Paris
    assert f"{WEB}/fr/compte/parametres/securite" in message.text
    assert "203.0.113" not in message.text
    assert message.html is not None and "203.0.113" not in message.html


async def test_new_country_sends_alert(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user_id = await _user(sessionmaker)
    await _session(sessionmaker, user_id, at=T0 - timedelta(days=10))
    session_id = await _session(sessionmaker, user_id, at=T0, country="DE")
    queue = await _alert(sessionmaker, user_id, session_id)
    assert len(queue.jobs) == 1
    assert "DE" in open_email(queue.jobs[0][1][0], settings=SETTINGS).text


async def test_device_not_seen_for_90_days_sends_alert(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _user(sessionmaker)
    await _session(sessionmaker, user_id, at=T0 - timedelta(days=91))
    session_id = await _session(sessionmaker, user_id, at=T0)
    assert len((await _alert(sessionmaker, user_id, session_id)).jobs) == 1


async def test_unknown_session_is_ignored(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    user_id = await _user(sessionmaker)
    assert (await _alert(sessionmaker, user_id, new_id())).jobs == []
