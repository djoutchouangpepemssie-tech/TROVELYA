"""Erasure and purge of media (P2-T02c2): files of a deleted photo leave storage at the next
hourly run, its row after 30 days; an erased account's at once; uploads never completed and
avatar photos never chosen after 24 hours. A race with the worker."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import MemoryStorage, new_storage_key
from trovelya.modules.media.service.purge import purge_media
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]


async def _media(
    sessionmaker: Session,
    storage: MemoryStorage,
    owner: UUID,
    *,
    status: str = "ready",
    age: timedelta = timedelta(0),
    deleted_for: timedelta | None = None,
    purpose: str = "listing",
) -> tuple[UUID, list[str]]:
    """A media of `owner` created `age` ago, with its files in storage; returns its id and
    the keys of its files (original first)."""
    media_id, original = new_id(), new_storage_key()
    variants = [new_storage_key(), new_storage_key()] if status == "ready" else []
    async with sessionmaker() as db:
        now = await db.scalar(text("SELECT now()"))
        await db.execute(
            text(
                "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
                " status, sha256, exif_stripped, variants, rejection_reason, created_at,"
                " deleted_at, captured_at, moderation)"
                " VALUES (:id, :owner, 'image', :purpose, :key, 'image/jpeg', 1000, :status,"
                " :sha, :status = 'ready', CAST(:variants AS jsonb),"
                " CASE WHEN :status = 'rejected' THEN 'type_mismatch' END, :created, :deleted,"
                ' :created, \'{"duplicate_of": "x"}\')'
            ),
            {
                "id": media_id,
                "owner": owner,
                "purpose": purpose,
                "key": original,
                "status": status,
                "sha": b"\x01" * 32 if status == "ready" else None,
                "variants": "["
                + ",".join(
                    f'{{"format": "webp", "width": 320, "height": 240, "key": "{k}", "bytes": 1}}'
                    for k in variants
                )
                + "]",
                "created": now - age,
                "deleted": None if deleted_for is None else now - deleted_for,
            },
        )
        await db.commit()
    await storage.put("originals", original, b"original", content_type="image/jpeg")
    for key in variants:
        await storage.put("variants", key, b"variant", content_type="image/webp")
    return media_id, [original, *variants]


async def _row(sessionmaker: Session, media_id: UUID) -> Any:
    async with sessionmaker() as db:
        return (
            await db.execute(
                text(
                    "SELECT deleted_at, files_deleted_at, variants, captured_at, moderation"
                    " FROM media WHERE id = :id"
                ),
                {"id": media_id},
            )
        ).one_or_none()


def _stored(storage: MemoryStorage, keys: list[str]) -> list[bool]:
    return [any(key == k for _, k in storage.objects) for key in keys]


async def _purge(sessionmaker: Session, storage: MemoryStorage) -> int:
    """Other tests' rows may be purged too: the tests check their own rows, never a count."""
    async with sessionmaker() as db:
        now = await db.scalar(text("SELECT now()"))
    return await purge_media(sessionmaker, storage, clock=FixedClock(now))


async def _set_avatar(sessionmaker: Session, user_id: UUID, media_id: UUID) -> None:
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE users SET avatar_media_id = :m WHERE id = :u"),
            {"m": media_id, "u": user_id},
        )
        await db.commit()


class HookedStorage(MemoryStorage):
    """Runs `hook` (once) when an original is deleted: what else happens meanwhile."""

    def __init__(self, hook: Callable[[], Awaitable[None]]) -> None:
        super().__init__()
        self.hook: Callable[[], Awaitable[None]] | None = hook

    async def delete(self, bucket: Any, key: str) -> None:
        if bucket == "originals" and self.hook is not None:
            hook, self.hook = self.hook, None
            await hook()
        await super().delete(bucket, key)


class FailingStorage(MemoryStorage):
    def __init__(self) -> None:
        super().__init__()
        self.failing = True

    async def delete(self, bucket: Any, key: str) -> None:
        if self.failing:
            raise ConnectionError("storage unreachable")
        await super().delete(bucket, key)


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


async def test_media_erased_from_storage(sessionmaker: Session, storage: MemoryStorage) -> None:
    """The account's eraser (run within the erasure) hides every photo and clears what it says
    of the person; the next purge removes files and rows, without waiting for the retention."""
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    photos = [await _media(sessionmaker, storage, member.id) for _ in range(2)]
    upload = await _media(sessionmaker, storage, member.id, status="uploading")
    kept = await _media(sessionmaker, storage, other.id)
    async with sessionmaker() as db:
        await registered_erasers()["media"](db, member.id)
        await db.execute(
            text("UPDATE users SET status = 'deleted' WHERE id = :id"), {"id": member.id}
        )
        await db.commit()
    for media_id, _ in (*photos, upload):
        row = await _row(sessionmaker, media_id)
        assert row.deleted_at is not None
        assert (row.captured_at, row.moderation) == (None, {})
    await _purge(sessionmaker, storage)
    for media_id, keys in (*photos, upload):
        assert await _row(sessionmaker, media_id) is None
        assert not any(_stored(storage, keys))
    row = await _row(sessionmaker, kept[0])
    assert row.deleted_at is None and row.moderation and all(_stored(storage, kept[1]))


async def test_withdrawn_photo_leaves_storage_at_once(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    """ADR-0019: a withdrawn photo's public URL stops working at the next run; its row (no
    files) stays for the retention."""
    member = await make_account(sessionmaker, completed=True)
    recent = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(minutes=1))
    old = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(days=31))
    live = await _media(sessionmaker, storage, member.id, age=timedelta(days=400))
    await _set_avatar(sessionmaker, member.id, old[0])  # its avatar row still points at it
    await _purge(sessionmaker, storage)
    row = await _row(sessionmaker, recent[0])
    assert row.files_deleted_at is not None
    assert not any(_stored(storage, recent[1]))
    assert await _row(sessionmaker, old[0]) is None and not any(_stored(storage, old[1]))
    assert (await _row(sessionmaker, live[0])).deleted_at is None
    assert all(_stored(storage, live[1]))
    async with sessionmaker() as db:
        avatar = await db.scalar(
            text("SELECT avatar_media_id FROM users WHERE id = :u"), {"u": member.id}
        )
    assert avatar is None


async def test_abandoned_uploads_and_old_refusals_purged(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    member = await make_account(sessionmaker, completed=True)
    abandoned = await _media(
        sessionmaker, storage, member.id, status="uploading", age=timedelta(hours=25)
    )
    in_progress = await _media(
        sessionmaker, storage, member.id, status="uploading", age=timedelta(hours=23)
    )
    old_refusal = await _media(
        sessionmaker, storage, member.id, status="rejected", age=timedelta(days=31)
    )
    new_refusal = await _media(
        sessionmaker, storage, member.id, status="rejected", age=timedelta(days=29)
    )
    await _purge(sessionmaker, storage)
    for media_id, keys in (abandoned, old_refusal):
        assert await _row(sessionmaker, media_id) is None and not any(_stored(storage, keys))
    for media_id, _ in (in_progress, new_refusal):
        assert (await _row(sessionmaker, media_id)).deleted_at is None


async def test_files_kept_until_they_can_be_deleted(sessionmaker: Session) -> None:
    """Files first, then the row: a storage failure leaves both for the next run."""
    storage = FailingStorage()
    member = await make_account(sessionmaker, completed=True)
    media_id, keys = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(days=31))
    await _purge(sessionmaker, storage)
    assert (await _row(sessionmaker, media_id)).files_deleted_at is None
    storage.failing = False
    await _purge(sessionmaker, storage)
    assert await _row(sessionmaker, media_id) is None and not any(_stored(storage, keys))


async def test_avatar_photo_never_chosen_purged_after_24h(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    member = await make_account(sessionmaker, completed=True)
    chosen, unchosen, recent = [
        await _media(sessionmaker, storage, member.id, age=age, purpose="avatar")
        for age in (timedelta(days=3), timedelta(hours=25), timedelta(hours=23))
    ]
    await _set_avatar(sessionmaker, member.id, chosen[0])
    await _purge(sessionmaker, storage)
    assert (await _row(sessionmaker, unchosen[0])).files_deleted_at is not None
    assert not any(_stored(storage, unchosen[1]))
    for media_id, keys in (chosen, recent):
        assert (await _row(sessionmaker, media_id)).deleted_at is None
        assert all(_stored(storage, keys))


async def test_late_worker_cannot_make_a_purged_media_ready(sessionmaker: Session) -> None:
    """A photo still processing after 24 hours: the worker finishing while its files are being
    deleted cannot make it ready, so it deletes the variants it wrote (processing.py)."""
    decided: list[bool] = []
    media: list[UUID] = []

    async def worker_finishes() -> None:
        async with sessionmaker() as db:
            decided.append(
                await repository.mark_ready(
                    db,
                    media[0],
                    width=1,
                    height=1,
                    sha256=b"\x02" * 32,
                    perceptual_hash=0,
                    variants=[{"format": "webp", "width": 1, "height": 1, "key": "k", "bytes": 1}],
                    moderation={},
                )
            )
            await db.commit()

    storage = HookedStorage(worker_finishes)
    member = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(
        sessionmaker,
        storage,
        member.id,
        status="processing",
        age=timedelta(hours=25),
        purpose="avatar",
    )
    media.append(media_id)
    await _purge(sessionmaker, storage)
    assert decided == [False]
    assert await _row(sessionmaker, media_id) is None


async def test_retention_is_a_setting(sessionmaker: Session, storage: MemoryStorage) -> None:
    member = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(days=8))
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE platform_settings SET value = '7'"
                " WHERE key = 'retention.deleted_media_days'"
            )
        )
        await db.commit()
    try:
        await _purge(sessionmaker, storage)
        assert await _row(sessionmaker, media_id) is None
    finally:
        async with sessionmaker() as db:
            await db.execute(
                text(
                    "UPDATE platform_settings SET value = '30'"
                    " WHERE key = 'retention.deleted_media_days'"
                )
            )
            await db.commit()
