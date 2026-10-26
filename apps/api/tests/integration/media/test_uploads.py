"""Uploading a photo (P2-T02a3, ADR-0019): a presigned URL, then « complete » hands the file
to the worker; the member reads its status. Nobody else ever sees it."""

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
from tests.integration.identity.test_profile import T0, make_account
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.media.adapters.storage import MemoryStorage
from trovelya.shared.clock import FixedClock

JPEG = {"purpose": "listing", "mime_type": "image/jpeg", "bytes": 2_000_000}
MAX_BYTES = 15 * 1024 * 1024


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...]]] = []

    async def enqueue_job(self, function: str, *args: object) -> None:
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
    app = create_app(make_settings(media_public_url="https://media.example"))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = clock
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    app.state.queue = queue
    app.state.storage = MemoryStorage()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


async def _upload(client: AsyncClient, headers: dict[str, str], **body: Any) -> Any:
    return await client.post("/v1/media/uploads", headers=headers, json=JPEG | body)


async def _row(sessionmaker: async_sessionmaker[AsyncSession], media_id: str) -> Any:
    async with sessionmaker() as db:
        return (
            await db.execute(text("SELECT * FROM media WHERE id = :id"), {"id": UUID(media_id)})
        ).one()


async def test_upload_returns_a_presigned_url(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    member = await make_account(sessionmaker, completed=True)
    response = await _upload(client, member.headers)
    assert response.status_code == 201
    body = response.json()
    assert body["headers"] == {"Content-Type": "image/jpeg"}
    assert body["expires_at"] == (T0 + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    row = await _row(sessionmaker, body["media_id"])
    assert (row.owner_id, row.status, row.purpose, row.mime_type, row.bytes) == (
        member.id,
        "uploading",
        "listing",
        "image/jpeg",
        2_000_000,
    )
    # The URL names the random key only: no member, no file name.
    assert body["upload_url"].startswith(f"memory://originals/{row.storage_key}?length=2000000")
    assert str(member.id) not in body["upload_url"]


@pytest.mark.parametrize(
    "mime_type", ["image/svg+xml", "image/gif", "image/heic", "application/pdf", "text/html"]
)
async def test_declared_type_whitelist(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], mime_type: str
) -> None:
    member = await make_account(sessionmaker, completed=True)
    response = await _upload(client, member.headers, mime_type=mime_type)
    assert (response.status_code, response.json()["code"]) == (422, "media_type_rejected")


async def test_declared_size_limit(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    member = await make_account(sessionmaker, completed=True)
    assert (await _upload(client, member.headers, bytes=MAX_BYTES)).status_code == 201
    too_large = await _upload(client, member.headers, bytes=MAX_BYTES + 1)
    assert (too_large.status_code, too_large.json()["code"]) == (413, "media_too_large")
    empty = await _upload(client, member.headers, bytes=0)
    assert empty.status_code == 422


async def test_only_listing_and_avatar_photos_in_p2(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    member = await make_account(sessionmaker, completed=True)
    assert (await _upload(client, member.headers, purpose="avatar")).status_code == 201
    for purpose in ("verification_video", "message", "dispute_evidence"):
        assert (await _upload(client, member.headers, purpose=purpose)).status_code == 422


async def test_upload_quota_per_hour_and_day(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    member = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE platform_settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
            [{"k": "media.uploads_per_hour", "v": "3"}, {"k": "media.uploads_per_day", "v": "5"}],
        )
        await db.commit()
    try:
        for _ in range(3):
            assert (await _upload(client, member.headers)).status_code == 201
        refused = await _upload(client, member.headers)
        assert (refused.status_code, refused.json()["code"]) == (429, "upload_limit")
        clock.advance(timedelta(hours=1, seconds=1))
        for _ in range(2):
            assert (await _upload(client, member.headers)).status_code == 201
        assert (await _upload(client, member.headers)).status_code == 429  # 5 today
        other = await make_account(sessionmaker, completed=True)
        assert (await _upload(client, other.headers)).status_code == 201  # per account
    finally:
        async with sessionmaker() as db:
            await db.execute(
                text("UPDATE platform_settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
                [
                    {"k": "media.uploads_per_hour", "v": "30"},
                    {"k": "media.uploads_per_day", "v": "200"},
                ],
            )
            await db.commit()


async def test_upload_needs_a_completed_profile(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    newcomer = await make_account(sessionmaker, completed=False)
    response = await _upload(client, newcomer.headers)
    assert (response.status_code, response.json()["code"]) == (403, "profile_incomplete")


async def test_complete_hands_the_file_to_the_worker_once(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    queue: RecordingQueue,
) -> None:
    member = await make_account(sessionmaker, completed=True)
    media_id = (await _upload(client, member.headers)).json()["media_id"]
    done = await client.post(f"/v1/media/{media_id}/complete", headers=member.headers)
    assert done.status_code == 202
    assert done.json()["status"] == "processing"
    assert queue.jobs == [("process_media", (media_id,))]
    again = await client.post(f"/v1/media/{media_id}/complete", headers=member.headers)
    assert (again.status_code, again.json()["code"]) == (409, "media_already_completed")
    assert len(queue.jobs) == 1
    assert (await _row(sessionmaker, media_id)).status == "processing"


async def test_someone_elses_media_is_not_found(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    queue: RecordingQueue,
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    intruder = await make_account(sessionmaker, completed=True)
    media_id = (await _upload(client, owner.headers)).json()["media_id"]
    for method, path in (
        ("POST", f"/v1/media/{media_id}/complete"),
        ("GET", f"/v1/media/{media_id}"),
    ):
        response = await client.request(method, path, headers=intruder.headers)
        assert response.status_code == 404, path
    assert queue.jobs == []
    assert (await _row(sessionmaker, media_id)).status == "uploading"


async def test_read_status_variants_and_reason(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    member = await make_account(sessionmaker, completed=True)
    ready_id = (await _upload(client, member.headers)).json()["media_id"]
    rejected_id = (await _upload(client, member.headers)).json()["media_id"]
    variants = '[{"format":"webp","width":320,"height":240,"key":"' + "b" * 32 + '","bytes":10}]'
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE media SET status = 'ready', sha256 = :h, exif_stripped = true,"
                " variants = CAST(:v AS jsonb), width = 4000, height = 3000 WHERE id = :id"
            ),
            {"h": b"\x01" * 32, "v": variants, "id": UUID(ready_id)},
        )
        await db.execute(
            text(
                "UPDATE media SET status = 'rejected', rejection_reason = 'type_mismatch'"
                " WHERE id = :id"
            ),
            {"id": UUID(rejected_id)},
        )
        await db.commit()
    ready = (await client.get(f"/v1/media/{ready_id}", headers=member.headers)).json()
    assert ready["status"] == "ready"
    assert ready["variants"] == [
        {
            "format": "webp",
            "width": 320,
            "height": 240,
            "url": "https://media.example/" + "b" * 32,
        }
    ]
    assert "storage_key" not in ready and "sha256" not in ready
    rejected = (await client.get(f"/v1/media/{rejected_id}", headers=member.headers)).json()
    assert (rejected["status"], rejected["rejection_reason"], rejected["variants"]) == (
        "rejected",
        "type_mismatch",
        [],
    )
    uploading_id = (await _upload(client, member.headers)).json()["media_id"]
    uploading = (await client.get(f"/v1/media/{uploading_id}", headers=member.headers)).json()
    assert (uploading["status"], uploading["variants"]) == ("uploading", [])
