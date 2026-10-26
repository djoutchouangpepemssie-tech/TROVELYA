"""GDPR erasure with a 30-day grace period, then anonymisation (P1-T09b, Q10)."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_profile import POLICY, T0, Account, make_account
from trovelya.core.email import open_email
from trovelya.core.flags import FlagService
from trovelya.core.gdpr import registered_erasers
from trovelya.main import create_app
from trovelya.modules.identity.service import create_session, process_erasures
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

WEB = "https://web.example.test"
SETTINGS = make_settings(web_origin=WEB)
GRACE = timedelta(days=30)
_OWNED_ROWS = {
    "sessions": "SELECT count(*) FROM sessions WHERE user_id = :id",
    "user_preferences": "SELECT count(*) FROM user_preferences WHERE user_id = :id",
    "passkeys": "SELECT count(*) FROM passkeys WHERE user_id = :id",
    "auth_identities": "SELECT count(*) FROM auth_identities WHERE user_id = :id",
    "user_roles": "SELECT count(*) FROM user_roles WHERE user_id = :id",
}


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))

    def emails(self) -> list[Any]:
        return [
            open_email(args[0], settings=SETTINGS)
            for function, args in self.jobs
            if function == "deliver_email"
        ]


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


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


async def _execute(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def _sign_in_again(
    sessionmaker: async_sessionmaker[AsyncSession], account: Account, clock: FixedClock
) -> Account:
    """A new strong sign-in (magic link or passkey) during the grace period."""
    async with sessionmaker() as db:
        issued = await create_session(
            db,
            user_id=account.id,
            kind="web",
            ip="203.0.113.9",
            user_agent=None,
            country="FR",
            strong=True,
            policy=POLICY,
            clock=clock,
        )
        await db.commit()
    return Account(account.id, account.email, issued.token)


async def _request_erasure(client: AsyncClient, account: Account) -> dict[str, Any]:
    response = await client.post("/v1/me/erasure", headers=account.headers)
    assert response.status_code == 202, response.text
    return response.json()


async def test_erasure_requires_step_up(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    account = await make_account(sessionmaker, completed=True)
    clock.advance(timedelta(hours=13))
    response = await client.post("/v1/me/erasure", headers=account.headers)
    assert response.status_code == 403 and response.json()["code"] == "step_up_required"
    assert (
        await _scalar(
            sessionmaker, "SELECT erasure_requested_at FROM users WHERE id = :id", id=account.id
        )
        is None
    )


async def test_erasure_revokes_sessions_and_hides_profile(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    username = f"efface_test_{new_id().hex[-8:]}"
    account = await make_account(sessionmaker, username=username, completed=True)
    assert (await client.get(f"/v1/users/{username}")).status_code == 200

    response = await client.post("/v1/me/erasure", headers=account.headers)
    assert response.status_code == 202, response.text
    assert response.json()["erase_at"] == (T0 + GRACE).isoformat().replace("+00:00", "Z")
    assert "__Host-trv_session=" in response.headers["set-cookie"]  # cleared

    assert (await client.get("/v1/me", headers=account.headers)).status_code == 401
    assert (await client.get(f"/v1/users/{username}")).status_code == 404
    [confirmation] = queue.emails()
    assert confirmation.to == account.email
    assert "23 novembre 2026" in confirmation.text
    assert f"{WEB}/fr/connexion" in confirmation.text
    # Signing in is not enough: the cancellation is a click (POST /v1/me/erasure/cancel).
    assert "« Annuler la suppression »" in confirmation.text
    assert "« Annuler la suppression »" in confirmation.html


async def test_cancel_during_grace(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
) -> None:
    username = f"annule_{new_id().hex[-8:]}"
    account = await make_account(sessionmaker, username=username, completed=True)
    await _request_erasure(client, account)
    clock.advance(timedelta(days=10))
    again = await _sign_in_again(sessionmaker, account, clock)
    me = (await client.get("/v1/me", headers=again.headers)).json()
    assert me["erasure_requested_at"] is not None  # the client offers to cancel
    assert me["erase_at"] == (T0 + GRACE).isoformat().replace("+00:00", "Z")
    listed = (await client.get("/v1/me/data-requests", headers=again.headers)).json()
    assert listed["erasure_grace_days"] == 30

    cancelled = await client.post("/v1/me/erasure/cancel", headers=again.headers)
    assert cancelled.status_code == 204, cancelled.text
    after = (await client.get("/v1/me", headers=again.headers)).json()
    assert after["erasure_requested_at"] is None and after["erase_at"] is None
    assert (await client.get(f"/v1/users/{username}")).status_code == 200

    # Nothing to cancel any more.
    nothing = await client.post("/v1/me/erasure/cancel", headers=again.headers)
    assert nothing.status_code == 409 and nothing.json()["code"] == "no_erasure_pending"

    clock.advance(GRACE)
    await process_erasures(sessionmaker, clock=clock)
    status = await _scalar(
        sessionmaker, "SELECT status::text FROM users WHERE id = :id", id=account.id
    )
    assert status == "active"


async def test_erasure_after_30_days_anonymises(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    account = await make_account(sessionmaker, completed=True)
    await _execute(
        sessionmaker,
        "INSERT INTO consents (id, user_id, anonymous_id, purpose, granted, policy_version, source)"
        " VALUES (:id, :u, 'anon-cookie-value-0123456789', 'analytics', true, 'v1', 'web')",
        id=new_id(),
        u=account.id,
    )
    await _request_erasure(client, account)

    clock.advance(GRACE - timedelta(seconds=1))
    assert await process_erasures(sessionmaker, clock=clock) == 0
    clock.advance(timedelta(seconds=2))
    assert await process_erasures(sessionmaker, clock=clock) == 1

    async with sessionmaker() as db:
        user = (
            await db.execute(
                text(
                    "SELECT email::text AS email, username::text AS username, display_name, bio,"
                    " birth_year, phone_e164, last_seen_at, status::text AS status, deleted_at"
                    " FROM users WHERE id = :id"
                ),
                {"id": account.id},
            )
        ).one()
        consents = (
            await db.execute(
                text("SELECT purpose, anonymous_id FROM consents WHERE user_id = :id"),
                {"id": account.id},
            )
        ).all()
        request_status = await db.scalar(
            text("SELECT status FROM data_requests WHERE user_id = :id AND kind = 'erasure'"),
            {"id": account.id},
        )
    assert user.email == f"efface+{account.id.hex}@invalid"
    assert user.username == f"efface_{account.id.hex[-8:]}"
    assert user.display_name == "Compte supprimé"
    assert (user.bio, user.birth_year, user.phone_e164, user.last_seen_at) == (None,) * 4
    assert user.status == "deleted" and user.deleted_at == clock.now()
    # Consents are kept as proof, with the internal identifier only.
    assert [(c.purpose, c.anonymous_id) for c in consents] == [("analytics", None)]
    assert request_status == "completed"
    for table, sql in _OWNED_ROWS.items():
        assert await _scalar(sessionmaker, sql, id=account.id) == 0, table


# Every column of every table in `public` (but the audit log), as text, matched against the
# person's former values. Built with format() in SQL: no string assembled in Python.
_FIND_VALUES = """
WITH cols AS MATERIALIZED (
  SELECT c.table_name, c.column_name
  FROM information_schema.columns c
  JOIN information_schema.tables t
    ON t.table_schema = c.table_schema AND t.table_name = c.table_name
  WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
    AND c.table_name <> 'audit_log' AND c.data_type <> 'bytea'
)
SELECT table_name, column_name FROM cols
WHERE (xpath('/row/n/text()', query_to_xml(format(
    'SELECT count(*) AS n FROM public.%I WHERE %I::text ILIKE ANY (%L)',
    table_name, column_name, CAST(:patterns AS text[])), false, true, '')))[1]::text::int > 0
"""


async def test_no_personal_value_left(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    marker = new_id().hex[-10:]
    email = f"perso_{marker}@example.org"
    username = f"perso_{marker}"
    display_name = f"Personne {marker}"
    account = await make_account(sessionmaker, email=email, username=username, completed=True)
    other = await make_account(sessionmaker, completed=True)
    await _execute(
        sessionmaker,
        "UPDATE users SET display_name = :d, bio = :b WHERE id = :id",
        d=display_name,
        b=f"Collectionneur {marker}",
        id=account.id,
    )
    for sql in (
        "INSERT INTO addresses (id, user_id, full_name, line1, postal_code, city, country_code)"
        " VALUES (:new, :u, :name, '12 rue ' || :m, '69007', 'Lyon', 'FR')",
        "INSERT INTO search_zones (id, user_id, label, place_name, center, radius_m, is_default)"
        " VALUES (:new, :u, 'Maison ' || :m, 'Lyon 7e', ST_MakePoint(4.84, 45.74)::geography,"
        " 5000, true)",
        "INSERT INTO passkeys (id, user_id, credential_id, public_key, sign_count, name)"
        " VALUES (:new, :u, '\\x01'::bytea, '\\x02'::bytea, 0, 'Téléphone ' || :m)",
        "INSERT INTO auth_identities (id, user_id, provider, provider_subject)"
        " VALUES (:new, :u, 'google', 'sub-' || :m)",
        "INSERT INTO magic_links (id, email, token_hash, purpose, expires_at)"
        " VALUES (:new, :email, '\\x03'::bytea, 'login', now())",
        "INSERT INTO follows (follower_id, followee_user_id) VALUES (:u, :other), (:other, :u)",
        "INSERT INTO blocks (blocker_id, blocked_id) VALUES (:u, :other)",
    ):
        await _execute(
            sessionmaker,
            sql,
            new=new_id(),
            u=account.id,
            other=other.id,
            m=marker,
            name=display_name,
            email=email,
        )
    await _request_erasure(client, account)
    clock.advance(GRACE + timedelta(seconds=1))
    await process_erasures(sessionmaker, clock=clock)

    async with sessionmaker() as db:
        found = (
            await db.execute(
                text(_FIND_VALUES),
                {"patterns": [f"%{marker}%", f"%{email}%"]},
            )
        ).all()
    assert [tuple(row) for row in found] == []


async def test_erasure_idempotent(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    account = await make_account(sessionmaker, completed=True)
    first = await _request_erasure(client, account)
    clock.advance(timedelta(days=1))
    again = await _sign_in_again(sessionmaker, account, clock)
    second = await _request_erasure(client, again)
    assert second["erase_at"] == first["erase_at"]  # the first request's date stands
    requests = await _scalar(
        sessionmaker,
        "SELECT count(*) FROM data_requests WHERE user_id = :id AND kind = 'erasure'",
        id=account.id,
    )
    assert requests == 1
    clock.advance(GRACE)
    assert await process_erasures(sessionmaker, clock=clock) >= 1
    assert await process_erasures(sessionmaker, clock=clock) == 0


async def test_erasure_event_and_audit(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    account = await make_account(sessionmaker, completed=True)
    await _request_erasure(client, account)
    clock.advance(GRACE + timedelta(seconds=1))
    await process_erasures(sessionmaker, clock=clock)
    events = await _scalar(
        sessionmaker,
        "SELECT count(*) FROM outbox_events WHERE aggregate_id = :id AND type = 'user.deleted'",
        id=account.id,
    )
    assert events == 1
    async with sessionmaker() as db:
        actions = (
            await db.execute(
                text(
                    "SELECT action, actor_type FROM audit_log"
                    " WHERE target_type = 'user' AND target_id = :id ORDER BY id"
                ),
                {"id": str(account.id)},
            )
        ).all()
    assert [(a.action, a.actor_type) for a in actions] == [
        ("user.erasure_requested", "user"),
        ("user.erase", "system"),
    ]
    assert set(registered_erasers()) >= {"identity", "media", "catalog"}


async def test_erased_account_cannot_sign_in_with_its_old_session(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    account = await make_account(sessionmaker, completed=True)
    await _request_erasure(client, account)
    again = await _sign_in_again(sessionmaker, account, clock)
    clock.advance(GRACE + timedelta(seconds=1))
    await process_erasures(sessionmaker, clock=clock)
    assert (await client.get("/v1/me", headers=again.headers)).status_code == 401
    user_id = await _scalar(sessionmaker, "SELECT id FROM users WHERE email = :e", e=account.email)
    assert user_id is None
    assert isinstance(account.id, UUID)
