"""Erasure and purge of media (P2-T02c2): files of a deleted photo leave storage at the next
hourly run, its row after 30 days; an erased account's at once; uploads never completed and
avatar photos never chosen after 24 hours. Races with the worker and with the avatar choice."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import make_account
from trovelya.core.errors import AppError
from trovelya.core.gdpr import registered_erasers
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.storage import MemoryStorage, new_storage_key
from trovelya.modules.media.service import purge
from trovelya.modules.media.service.avatars import check_avatar
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
    """Fails to delete the originals in `failing` (every original when None)."""

    def __init__(self, failing: set[str] | None = None) -> None:
        super().__init__()
        self.failing = failing
        self.attempts = 0

    async def delete(self, bucket: Any, key: str) -> None:
        if bucket == "originals":
            self.attempts += 1
            if self.failing is None or key in self.failing:
                raise ConnectionError("storage unreachable")
        await super().delete(bucket, key)


class _Recorder:
    def __init__(self) -> None:
        self.errors: list[tuple[str, dict[str, Any]]] = []

    def error(self, event: str, **fields: Any) -> None:
        self.errors.append((event, fields))

    def exception(self, event: str, **fields: Any) -> None:
        pass

    def info(self, event: str, **fields: Any) -> None:
        pass


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
    storage.failing = set()
    await _purge(sessionmaker, storage)
    assert await _row(sessionmaker, media_id) is None and not any(_stored(storage, keys))


async def test_failing_files_retried_after_the_others(
    sessionmaker: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files that keep failing stop a run (failures in a row, across batches), then are
    retried after the others: a newer withdrawn photo still leaves storage at the next run."""
    monkeypatch.setattr(purge, "BATCH", 2)
    monkeypatch.setattr(purge, "MAX_CONSECUTIVE_FAILURES", 3)
    storage = FailingStorage(set())
    member = await make_account(sessionmaker, completed=True)
    failing = [
        await _media(sessionmaker, storage, member.id, deleted_for=timedelta(hours=1))
        for _ in range(3)
    ]
    storage.failing = {keys[0] for _, keys in failing}
    newer = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(minutes=1))
    await _purge(sessionmaker, storage)
    assert (await _row(sessionmaker, newer[0])).files_deleted_at is None  # the run stopped
    await _purge(sessionmaker, storage)
    assert (await _row(sessionmaker, newer[0])).files_deleted_at is not None
    for media_id, _ in failing:
        assert (await _row(sessionmaker, media_id)).files_deleted_at is None


async def test_only_failures_in_a_row_stop_the_run(
    sessionmaker: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(purge, "MAX_CONSECUTIVE_FAILURES", 2)
    storage = FailingStorage(set())
    member = await make_account(sessionmaker, completed=True)
    media = [
        await _media(sessionmaker, storage, member.id, deleted_for=timedelta(hours=1))
        for _ in range(6)
    ]
    storage.failing = {keys[0] for _, keys in media[0::2]}
    await _purge(sessionmaker, storage)
    for media_id, _ in media[1::2]:
        assert (await _row(sessionmaker, media_id)).files_deleted_at is not None


async def test_storage_down_stops_the_run(
    sessionmaker: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(purge, "MAX_CONSECUTIVE_FAILURES", 3)
    storage = FailingStorage()
    member = await make_account(sessionmaker, completed=True)
    for _ in range(5):
        await _media(sessionmaker, storage, member.id, deleted_for=timedelta(hours=1))
    await _purge(sessionmaker, storage)
    assert storage.attempts == 3


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


async def test_photo_being_chosen_as_avatar_is_not_purged(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    """The member first: `check_avatar` holds the photo while the profile is saved; the purge
    skips it, then sees it chosen."""
    member = await make_account(sessionmaker, completed=True)
    media_id, keys = await _media(
        sessionmaker, storage, member.id, age=timedelta(hours=25), purpose="avatar"
    )
    async with sessionmaker() as db:
        await check_avatar(db, owner_id=member.id, media_id=media_id)
        # Waiting for the lock would hang the purge: it must skip the photo instead.
        await asyncio.wait_for(_purge(sessionmaker, storage), timeout=10)
        await db.execute(
            text("UPDATE users SET avatar_media_id = :m WHERE id = :u"),
            {"m": media_id, "u": member.id},
        )
        await db.commit()
    await _purge(sessionmaker, storage)
    assert (await _row(sessionmaker, media_id)).deleted_at is None and all(_stored(storage, keys))


async def test_photo_purged_first_cannot_be_chosen(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    """The purge first: choosing the photo waits for it, then finds it gone (404)."""
    member = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(
        sessionmaker, storage, member.id, age=timedelta(hours=25), purpose="avatar"
    )
    async with sessionmaker() as purging, sessionmaker() as choosing:
        now = await purging.scalar(text("SELECT now()"))
        await repository.mark_for_purge(
            purging,
            now=now,
            abandoned_before=now - timedelta(hours=24),
            refused_before=now - timedelta(days=30),
        )
        choice = asyncio.ensure_future(
            check_avatar(choosing, owner_id=member.id, media_id=media_id)
        )
        await asyncio.sleep(1)
        assert not choice.done()  # waiting for the purge
        await purging.commit()
        with pytest.raises(AppError) as refused:
            await asyncio.wait_for(choice, timeout=10)
    assert refused.value.status == 404


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


async def test_files_overdue_counted(sessionmaker: Session, storage: MemoryStorage) -> None:
    """Files of a media deleted 48 hours ago and more (any account) still stored."""

    async def overdue() -> int:
        async with sessionmaker() as db:
            now = await db.scalar(text("SELECT now()"))
            return await repository.files_overdue(db, deleted_before=now - timedelta(hours=48))

    member = await make_account(sessionmaker, completed=True)
    before = await overdue()
    await _media(sessionmaker, storage, member.id, deleted_for=timedelta(hours=47))
    await _media(sessionmaker, storage, member.id, age=timedelta(days=5))
    gone, _ = await _media(sessionmaker, storage, member.id, deleted_for=timedelta(hours=49))
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE media SET files_deleted_at = now() WHERE id = :id"), {"id": gone}
        )
        await db.commit()
    assert await overdue() == before
    await _media(sessionmaker, storage, member.id, deleted_for=timedelta(hours=49))
    assert await overdue() == before + 1


async def test_files_overdue_reported(
    sessionmaker: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counted 48 hours after the deletion, and reported."""
    recorder, thresholds = _Recorder(), list[timedelta]()
    monkeypatch.setattr(purge, "logger", recorder)
    files_overdue = repository.files_overdue

    async def spy(db: AsyncSession, *, deleted_before: Any) -> int:
        thresholds.append(await db.scalar(text("SELECT now()")) - deleted_before)
        return await files_overdue(db, deleted_before=deleted_before)

    monkeypatch.setattr(repository, "files_overdue", spy)
    storage = FailingStorage()
    member = await make_account(sessionmaker, completed=True)
    await _media(sessionmaker, storage, member.id, deleted_for=timedelta(hours=49))
    await _purge(sessionmaker, storage)
    assert [event for event, _ in recorder.errors][-1] == "media.files_overdue"
    [threshold] = thresholds
    assert timedelta(hours=48) <= threshold < timedelta(hours=48, minutes=1)


async def test_chosen_avatars_not_locked_by_the_purge(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    """The purge locks only the avatar photos nobody chose: the others stay free for the
    profile and the foreign keys pointing at them."""
    member = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(
        sessionmaker, storage, member.id, age=timedelta(days=10), purpose="avatar"
    )
    await _set_avatar(sessionmaker, member.id, media_id)
    async with sessionmaker() as purging, sessionmaker() as other:
        now = await purging.scalar(text("SELECT now()"))
        await repository.mark_for_purge(
            purging,
            now=now,
            abandoned_before=now - timedelta(hours=24),
            refused_before=now - timedelta(days=30),
        )
        await other.execute(
            text("SELECT 1 FROM media WHERE id = :id FOR SHARE NOWAIT"), {"id": media_id}
        )
        await purging.rollback()
