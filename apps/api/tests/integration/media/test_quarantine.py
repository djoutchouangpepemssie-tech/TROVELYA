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


async def _sql(sessionmaker: Session, sql: str, media_id: object) -> object:
    async with sessionmaker() as db:
        value = (await db.execute(text(sql), {"m": media_id})).scalar()  # UPDATE: RETURNING id
        await db.commit()
        return value


async def test_half_made_copy_goes_with_the_photo(sessionmaker: Session) -> None:
    """A move cut short (copy made, public variant left) then the photo deleted: no copy stays."""
    storage = MemoryStorage()
    media_id, keys = await _media(sessionmaker, storage, (await make_account(sessionmaker)).id)
    await _quarantine(sessionmaker, [media_id])
    await storage.put("originals", keys[1], b"copy", content_type="image/webp")
    await _sql(
        sessionmaker, "UPDATE media SET deleted_at = now() WHERE id = :m RETURNING id", media_id
    )
    await _purge(sessionmaker, storage)
    assert not any(_in(storage, "originals", keys) + _in(storage, "variants", keys))


async def test_private_copy_keeps_its_type(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    media_id, keys = await _media(sessionmaker, storage, (await make_account(sessionmaker)).id)
    avif = "UPDATE media SET variants = jsonb_set(variants, '{0,format}', '\"avif\"')"
    await _sql(sessionmaker, avif + " WHERE id = :m RETURNING id", media_id)
    await _quarantine(sessionmaker, [media_id])
    await _purge(sessionmaker, storage)
    kinds = [storage.objects[("originals", key)][1] for key in keys[1:]]
    assert kinds == ["image/avif", "image/webp"]


class _Failing(MemoryStorage):
    failing = ""

    async def get(self, bucket: str, key: str) -> bytes:  # type: ignore[override]
        if key == self.failing:
            raise OSError("storage error")
        return await super().get(bucket, key)  # type: ignore[arg-type]


async def test_failing_photo_holds_back_no_other(sessionmaker: Session) -> None:
    storage, owner = _Failing(), (await make_account(sessionmaker)).id
    stuck, stuck_keys = await _media(sessionmaker, storage, owner)
    moved, moved_keys = await _media(sessionmaker, storage, owner)
    storage.failing = stuck_keys[1]
    await _quarantine(sessionmaker, [stuck, moved])
    await _purge(sessionmaker, storage)
    assert all(_in(storage, "originals", moved_keys[1:]))
    assert not any(_in(storage, "variants", moved_keys[1:]))
    sql = "SELECT quarantine_moved_at FROM media WHERE id = :m"
    assert await _sql(sessionmaker, sql, stuck) is None  # tried again at the next run
