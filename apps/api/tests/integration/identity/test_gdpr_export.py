"""Self-service GDPR export (P1-T09a, ADR-0016)."""

import io
import json
import re
import zipfile
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
from tests.integration.identity.test_profile import T0, Account, make_account
from trovelya.core.email import open_email
from trovelya.core.flags import FlagService
from trovelya.core.gdpr import registered_exporters
from trovelya.main import create_app
from trovelya.modules.identity.service import build_data_export, purge_expired_exports
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

WEB = "https://web.example.test"
SETTINGS = make_settings(web_origin=WEB)
EXPORT_JOB = "build_data_export"


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))

    def export_jobs(self) -> list[str]:
        return [args[0] for function, args in self.jobs if function == EXPORT_JOB]

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


async def _exported(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    account: Account,
    *,
    clock: FixedClock,
    queue: RecordingQueue,
) -> tuple[str, dict[str, Any], zipfile.ZipFile]:
    """Request an export, run the worker job, download the archive."""
    requested = await client.post("/v1/me/data-export", headers=account.headers)
    assert requested.status_code == 202, requested.text
    request_id = requested.json()["request_id"]
    assert queue.export_jobs()[-1] == request_id
    await build_data_export(
        sessionmaker, UUID(request_id), settings=SETTINGS, clock=clock, queue=queue
    )
    download = await client.get(
        f"/v1/me/data-export/{request_id}/download", headers=account.headers
    )
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    return request_id, json.loads(archive.read("export.json")), archive


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


async def _execute(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def test_export_flow(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    account = await make_account(sessionmaker, completed=True)
    request_id, export, archive = await _exported(
        client, sessionmaker, account, clock=clock, queue=queue
    )
    assert set(archive.namelist()) == {"export.json", "LISEZMOI.txt"}
    assert "TROVÉLYA" in archive.read("LISEZMOI.txt").decode()
    assert export["identity"]["users"][0]["email"] == account.email
    assert export["identity"]["data_requests"][0]["id"] == request_id

    [ready] = queue.emails()
    assert ready.to == account.email
    assert f"{WEB}/fr/compte/donnees" in ready.text

    listed = (await client.get("/v1/me/data-requests", headers=account.headers)).json()
    [entry] = listed["data"]
    assert (entry["id"], entry["kind"], entry["status"]) == (request_id, "export", "completed")
    assert entry["expires_at"] == (T0 + timedelta(days=7)).isoformat().replace("+00:00", "Z")


async def test_every_identity_table_exported(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    """Any table pointing at `users` must be in the export (introspection, ADR-0016)."""
    async with sessionmaker() as db:
        tables = set(
            (
                await db.scalars(
                    text(
                        "SELECT DISTINCT conrelid::regclass::text FROM pg_constraint"
                        " WHERE contype = 'f' AND confrelid = 'users'::regclass"
                    )
                )
            ).all()
        )
    account = await make_account(sessionmaker, completed=True)
    _, export, _ = await _exported(client, sessionmaker, account, clock=clock, queue=queue)
    assert tables | {"users"} <= set(export["identity"])
    assert set(registered_exporters()) >= {"identity"}


async def test_export_excludes_secrets_and_other_peoples_data(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    account = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    blocked = await make_account(sessionmaker, completed=True)
    await _execute(
        sessionmaker,
        "INSERT INTO passkeys (id, user_id, credential_id, public_key, sign_count, name)"
        " VALUES (:id, :u, '\\x0102'::bytea, '\\x0304'::bytea, 0, 'Mon téléphone')",
        id=new_id(),
        u=account.id,
    )
    await _execute(
        sessionmaker,
        "INSERT INTO blocks (blocker_id, blocked_id) VALUES (:me, :b), (:other, :me)",
        me=account.id,
        b=blocked.id,
        other=other.id,
    )
    await _execute(
        sessionmaker,
        "INSERT INTO follows (follower_id, followee_user_id) VALUES (:other, :me)",
        me=account.id,
        other=other.id,
    )
    _, export, archive = await _exported(client, sessionmaker, account, clock=clock, queue=queue)
    raw = archive.read("export.json").decode()
    for secret in ("token_hash", "public_key", "credential_id", "sign_count"):
        assert secret not in raw
    identity = export["identity"]
    assert [p["name"] for p in identity["passkeys"]] == ["Mon téléphone"]
    assert identity["sessions"] and "ip" in identity["sessions"][0]
    # My own blocks only: who blocked me stays private; followers are counted, not named.
    assert [b["blocked_id"] for b in identity["blocks"]] == [str(blocked.id)]
    assert str(other.id) not in raw
    assert identity["follows"] == {"following": [], "followers_count": 1}


async def test_second_export_while_pending_returns_existing(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, queue: RecordingQueue
) -> None:
    account = await make_account(sessionmaker, completed=True)
    first = await client.post("/v1/me/data-export", headers=account.headers)
    second = await client.post("/v1/me/data-export", headers=account.headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["request_id"] == second.json()["request_id"]
    assert len(queue.export_jobs()) == 1


async def test_export_and_download_require_step_up(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    account = await make_account(sessionmaker, completed=True)
    request_id = (await client.post("/v1/me/data-export", headers=account.headers)).json()[
        "request_id"
    ]
    await build_data_export(
        sessionmaker, UUID(request_id), settings=SETTINGS, clock=clock, queue=queue
    )
    clock.advance(timedelta(hours=13))
    for response in (
        await client.post("/v1/me/data-export", headers=account.headers),
        await client.get(f"/v1/me/data-export/{request_id}/download", headers=account.headers),
    ):
        assert response.status_code == 403 and response.json()["code"] == "step_up_required"
    # The list itself is not sensitive.
    assert (await client.get("/v1/me/data-requests", headers=account.headers)).status_code == 200


async def test_download_other_user_404(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    intruder = await make_account(sessionmaker, completed=True)
    request_id, _, _ = await _exported(client, sessionmaker, owner, clock=clock, queue=queue)
    for path in (
        f"/v1/me/data-export/{request_id}/download",
        f"/v1/me/data-export/{new_id()}/download",
    ):
        response = await client.get(path, headers=intruder.headers)
        assert response.status_code == 404


async def test_export_expires_7_days(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    account = await make_account(sessionmaker, completed=True)
    request_id, _, _ = await _exported(client, sessionmaker, account, clock=clock, queue=queue)
    path = f"/v1/me/data-export/{request_id}/download"
    clock.advance(timedelta(days=7, seconds=1))
    # A fresh strong sign-in, so that only the expiry answers.
    await _execute(
        sessionmaker,
        "UPDATE sessions SET mfa_at = :now, last_used_at = :now WHERE user_id = :u",
        now=clock.now(),
        u=account.id,
    )
    assert (await client.get(path, headers=account.headers)).status_code == 404
    assert await purge_expired_exports(sessionmaker, clock=clock) >= 1
    count = await _scalar(
        sessionmaker,
        "SELECT count(*) FROM data_exports WHERE data_request_id = :id",
        id=UUID(request_id),
    )
    assert count == 0
    # A new export can be asked for.
    again = await client.post("/v1/me/data-export", headers=account.headers)
    assert again.status_code == 202 and again.json()["request_id"] != request_id


async def test_export_audited(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    account = await make_account(sessionmaker, completed=True)
    request_id, _, _ = await _exported(client, sessionmaker, account, clock=clock, queue=queue)
    async with sessionmaker() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT action, actor_type, actor_id FROM audit_log"
                    " WHERE target_type = 'data_request' AND target_id = :id ORDER BY id"
                ),
                {"id": request_id},
            )
        ).all()
    assert [(r.action, r.actor_type) for r in rows] == [
        ("gdpr.export_requested", "user"),
        ("gdpr.export_built", "system"),
        ("gdpr.export_downloaded", "user"),
    ]
    assert rows[0].actor_id == account.id and rows[2].actor_id == account.id


async def test_export_archive_is_encrypted_at_rest(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    clock: FixedClock,
    queue: RecordingQueue,
) -> None:
    account = await make_account(sessionmaker, completed=True)
    request_id, _, _ = await _exported(client, sessionmaker, account, clock=clock, queue=queue)
    stored = await _scalar(
        sessionmaker,
        "SELECT ciphertext FROM data_exports WHERE data_request_id = :id",
        id=UUID(request_id),
    )
    assert not bytes(stored).startswith(b"PK")  # not a plain ZIP
    assert account.email.encode() not in bytes(stored)
    assert re.search(rb"export\.json", bytes(stored)) is None
