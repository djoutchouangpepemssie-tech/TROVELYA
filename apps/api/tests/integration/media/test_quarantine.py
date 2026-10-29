"""Photos of a listing removed by the moderation (P2-T05c1b, plan Q40): quarantined at once
(never shown again), their variants moved from the public bucket to a private copy at the next
hourly purge, kept for the appeal; the private copy goes with the photo's deletion."""

from datetime import timedelta

from sqlalchemy import text

from tests.integration.identity.test_profile import make_account
from tests.integration.media.test_media_purge import (
    Session,
    _media,  # pyright: ignore[reportPrivateUsage]
    _purge,  # pyright: ignore[reportPrivateUsage]
)
from trovelya.modules.media.adapters.storage import MemoryStorage
from trovelya.modules.media.service.listing_photos import photo_variants_by_id, quarantine_photos
from trovelya.shared.clock import FixedClock


def _in(storage: MemoryStorage, bucket: str, keys: list[str]) -> list[bool]:
    return [(bucket, key) in storage.objects for key in keys]


async def _quarantine(sessionmaker: Session, media_ids: list[object]) -> None:
    async with sessionmaker() as db:
        now = await db.scalar(text("SELECT now()"))
        await quarantine_photos(db, media_ids, now=now)  # type: ignore[arg-type]
        await db.commit()


async def test_quarantined_photo_never_shown_and_moved_private(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    member = await make_account(sessionmaker, completed=True)
    media_id, keys = await _media(sessionmaker, storage, member.id)
    variants = keys[1:]
    await _quarantine(sessionmaker, [media_id])
    async with sessionmaker() as db:
        assert await photo_variants_by_id(db, [media_id], public_url="https://cdn") == {}
    assert all(_in(storage, "variants", variants))  # until the next run
    await _purge(sessionmaker, storage)
    assert not any(_in(storage, "variants", variants))  # no public URL left
    assert all(_in(storage, "originals", variants))  # the private copy, for the appeal
    async with sessionmaker() as db:
        row = (
            await db.execute(
                text("SELECT deleted_at, quarantine_moved_at FROM media WHERE id = :m"),
                {"m": media_id},
            )
        ).one()
    assert row.deleted_at is None and row.quarantine_moved_at is not None
    await _purge(sessionmaker, storage)  # a second run moves nothing again
    assert all(_in(storage, "originals", variants))


async def test_private_copy_goes_with_the_photo(sessionmaker: Session) -> None:
    """The listing's retention ends (Q19): the photo is deleted, its private copy too."""
    storage = MemoryStorage()
    member = await make_account(sessionmaker, completed=True)
    media_id, keys = await _media(sessionmaker, storage, member.id)
    await _quarantine(sessionmaker, [media_id])
    await _purge(sessionmaker, storage)
    async with sessionmaker() as db:
        await db.execute(text("UPDATE media SET deleted_at = now() WHERE id = :m"), {"m": media_id})
        await db.commit()
    await _purge(sessionmaker, storage)
    assert not any(_in(storage, "originals", keys) + _in(storage, "variants", keys))


async def test_quarantine_is_idempotent(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    member = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, member.id)
    await _quarantine(sessionmaker, [media_id])
    async with sessionmaker() as db:
        first = await db.scalar(
            text("SELECT quarantined_at FROM media WHERE id = :m"), {"m": media_id}
        )
        later = FixedClock(first + timedelta(hours=1)).now()
        await quarantine_photos(db, [media_id], now=later)
        await db.commit()
        again = await db.scalar(
            text("SELECT quarantined_at FROM media WHERE id = :m"), {"m": media_id}
        )
    assert again == first
