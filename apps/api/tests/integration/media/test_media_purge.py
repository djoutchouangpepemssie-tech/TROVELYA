"""Erasure and purge of media (P2-T02c2): an erased account's photos leave storage at the
next purge; deleted photos after 30 days; uploads never completed after 24 hours."""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers
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
                " deleted_at, captured_at)"
                " VALUES (:id, :owner, 'image', 'listing', :key, 'image/jpeg', 1000, :status,"
                " :sha, :status = 'ready', CAST(:variants AS jsonb),"
                " CASE WHEN :status = 'rejected' THEN 'type_mismatch' END, :created, :deleted,"
                " :created)"
            ),
            {
                "id": media_id,
                "owner": owner,
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


async def _exists(sessionmaker: Session, media_id: UUID) -> bool:
    async with sessionmaker() as db:
        return bool(
            await db.scalar(
                text("SELECT EXISTS (SELECT 1 FROM media WHERE id = :id)"), {"id": media_id}
            )
        )


def _stored(storage: MemoryStorage, keys: list[str]) -> list[bool]:
    return [any(key == k for _, k in storage.objects) for key in keys]


async def _purge(sessionmaker: Session, storage: MemoryStorage) -> int:
    async with sessionmaker() as db:
        now = await db.scalar(text("SELECT now()"))
    return await purge_media(sessionmaker, storage, clock=FixedClock(now))


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


async def test_media_erased_from_storage(sessionmaker: Session, storage: MemoryStorage) -> None:
    """The account's eraser (run within the erasure) hides every photo at once; the purge
    then removes files and rows, without waiting for the 30-day retention."""
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
        hidden = await db.scalar(
            text(
                "SELECT bool_and(deleted_at IS NOT NULL AND captured_at IS NULL) FROM media"
                " WHERE owner_id = :id"
            ),
            {"id": member.id},
        )
    assert hidden
    assert await _purge(sessionmaker, storage) == 3
    for media_id, keys in (*photos, upload):
        assert not await _exists(sessionmaker, media_id)
        assert _stored(storage, keys) == [False] * len(keys)
    assert await _exists(sessionmaker, kept[0]) and all(_stored(storage, kept[1]))


async def test_purge_after_retention(sessionmaker: Session, storage: MemoryStorage) -> None:
    member = await make_account(sessionmaker, completed=True)
    recent = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(days=29))
    old = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(days=31))
    live = await _media(sessionmaker, storage, member.id, age=timedelta(days=400))
    async with sessionmaker() as db:  # the old one is still someone's avatar row
        await db.execute(
            text("UPDATE users SET avatar_media_id = :m WHERE id = :u"),
            {"m": old[0], "u": member.id},
        )
        await db.commit()
    assert await _purge(sessionmaker, storage) == 1
    assert not await _exists(sessionmaker, old[0]) and _stored(storage, old[1]) == [False] * 3
    for media_id, keys in (recent, live):
        assert await _exists(sessionmaker, media_id) and all(_stored(storage, keys))
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
    assert await _purge(sessionmaker, storage) == 2
    for media_id, keys in (abandoned, old_refusal):
        assert not await _exists(sessionmaker, media_id) and not any(_stored(storage, keys))
    for media_id, _ in (in_progress, new_refusal):
        assert await _exists(sessionmaker, media_id)


async def test_row_kept_while_its_files_cannot_be_deleted(sessionmaker: Session) -> None:
    """Files first, then the row: a storage failure leaves the row for the next purge."""

    class FailingStorage(MemoryStorage):
        async def delete(self, bucket: Any, key: str) -> None:
            raise ConnectionError("storage unreachable")

    storage = FailingStorage()
    member = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(days=31))
    assert await _purge(sessionmaker, storage) == 0
    assert await _exists(sessionmaker, media_id)
