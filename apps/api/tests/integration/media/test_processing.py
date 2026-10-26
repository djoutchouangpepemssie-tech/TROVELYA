"""The worker's `process_media` (P2-T02b2, ADR-0019): `processing` → `ready` with clean
variants in the public bucket, or `rejected` with a reason; the original never outlives it."""

import asyncio
import random
from datetime import timedelta
from io import BytesIO
from typing import Any
from uuid import UUID

import pytest
from arq import Retry
from PIL import Image, ImageDraw
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import T0, make_account
from trovelya.modules.media.adapters.storage import MemoryStorage, new_storage_key
from trovelya.modules.media.service import processing
from trovelya.modules.media.service.processing import process_media, recover_stuck_media
from trovelya.modules.media.tasks import process_media_job
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]


def _photo(scene: int = 0) -> bytes:
    """A reproducible picture per scene number: thirty random coloured blocks, so two scenes are
    as unlike as two photos (a plain gradient would give near-identical dHashes)."""
    rng = random.Random(scene)  # noqa: S311 — test pictures, not secrets
    image = Image.new("RGB", (800, 600), (128, 128, 128))
    draw = ImageDraw.Draw(image)
    for _ in range(30):
        x, y = rng.randrange(700), rng.randrange(500)
        colour = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        draw.rectangle((x, y, x + rng.randrange(50, 300), y + rng.randrange(50, 300)), fill=colour)
    out = BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def _encode(image: Image.Image) -> bytes:
    out = BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


class FlakyStorage(MemoryStorage):
    """MemoryStorage whose calls can fail once, or run a hook first (to change the database
    while the worker is between two steps)."""

    def __init__(self) -> None:
        super().__init__()
        self.fail: set[str] = set()  # "get", "put", "delete-originals"
        self.puts = 0
        self.before_get: Any = None

    async def get(self, bucket: Any, key: str, *, max_bytes: int | None = None) -> bytes:
        if self.before_get is not None:
            await self.before_get()
        if "get" in self.fail:
            raise ConnectionError("storage unreachable")
        return await super().get(bucket, key, max_bytes=max_bytes)

    async def put(self, bucket: Any, key: str, data: bytes, *, content_type: str) -> None:
        await super().put(bucket, key, data, content_type=content_type)
        if bucket == "variants":
            self.puts += 1
            if "put" in self.fail and self.puts == 3:
                raise ConnectionError("storage unreachable")

    async def delete(self, bucket: Any, key: str) -> None:
        if bucket == "originals" and "delete-originals" in self.fail:
            self.fail.discard("delete-originals")
            raise ConnectionError("storage unreachable")
        await super().delete(bucket, key)


async def _media(
    sessionmaker: Session,
    storage: MemoryStorage,
    owner_id: UUID,
    data: bytes | None,
    mime: str = "image/jpeg",
    status: str = "processing",
    purpose: str = "listing",
) -> tuple[UUID, str]:
    """A media row as `complete` leaves it, with its original in storage (None: never sent)."""
    media_id, key = new_id(), new_storage_key()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
                " status)"
                " VALUES (:id, :owner, 'image', :purpose, :key, :mime, :bytes, 'processing')"
            ),
            {
                "purpose": purpose,
                "id": media_id,
                "owner": owner_id,
                "key": key,
                "mime": mime,
                "bytes": len(data or b"x"),
            },
        )
        if status != "processing":  # as complete rows as the constraints require
            await db.execute(
                text(
                    "UPDATE media SET status = :status, sha256 = :h, exif_stripped = true,"
                    " variants = CAST(:v AS jsonb),"
                    " rejection_reason = CASE WHEN :status = 'rejected' THEN 'x' END"
                    " WHERE id = :id"
                ),
                {"status": status, "h": b"\x01" * 32, "v": '[{"format":"webp"}]', "id": media_id},
            )
        await db.commit()
    if data is not None:
        await storage.put("originals", key, data, content_type=mime)
    return media_id, key


async def _row(sessionmaker: Session, media_id: UUID) -> Any:
    async with sessionmaker() as db:
        return (
            await db.execute(text("SELECT * FROM media WHERE id = :id"), {"id": media_id})
        ).one()


async def _events(sessionmaker: Session, media_id: UUID) -> list[Any]:
    async with sessionmaker() as db:
        rows = await db.execute(
            text("SELECT type, payload FROM outbox_events WHERE aggregate_id = :id"),
            {"id": media_id},
        )
        return [tuple(r) for r in rows]


def _variant_keys(storage: MemoryStorage) -> set[str]:
    return {key for bucket, key in storage.objects if bucket == "variants"}


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


async def test_ready_with_clean_variants_and_hashes(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    media_id, key = await _media(sessionmaker, storage, owner.id, _photo())
    # Through the worker job, as `complete` enqueues it.
    ctx = {"sessionmaker": sessionmaker, "storage": storage, "job_try": 1}
    assert await process_media_job(ctx, str(media_id)) == "ready"
    row = await _row(sessionmaker, media_id)
    assert (row.status, row.width, row.height, row.exif_stripped) == ("ready", 800, 600, True)
    assert len(row.sha256) == 32 and row.perceptual_hash is not None
    assert [(v["format"], v["width"]) for v in row.variants] == [
        ("avif", 320),
        ("avif", 640),
        ("avif", 800),
        ("webp", 320),
        ("webp", 640),
        ("webp", 800),
    ]
    assert {v["key"] for v in row.variants} == _variant_keys(storage)
    for variant in row.variants:
        data, content_type = storage.objects[("variants", variant["key"])]
        assert (content_type, variant["bytes"]) == (f"image/{variant['format']}", len(data))
    assert ("originals", key) not in storage.objects  # the original never outlives processing
    assert await _events(sessionmaker, media_id) == [
        ("media.ready", {"media_id": str(media_id), "owner_id": str(owner.id), "v": 1})
    ]


@pytest.mark.parametrize(
    ("data", "mime", "reason"),
    [
        (b"#!/bin/sh\necho owned\n" * 10, "image/jpeg", "type_mismatch"),
        (_photo()[:2000], "image/jpeg", "unreadable"),
        (None, "image/jpeg", "missing_file"),
    ],
    ids=["spoofed", "truncated", "never-sent"],
)
async def test_rejected_with_a_reason(
    sessionmaker: Session,
    storage: MemoryStorage,
    data: bytes | None,
    mime: str,
    reason: str,
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, owner.id, data, mime)
    assert await process_media(sessionmaker, storage, media_id) == "rejected"
    row = await _row(sessionmaker, media_id)
    assert (row.status, row.rejection_reason, row.variants) == ("rejected", reason, [])
    assert not storage.objects  # nothing served, original gone
    assert await _events(sessionmaker, media_id) == [
        ("media.rejected", {"media_id": str(media_id), "reason": reason, "v": 1})
    ]


async def test_rejects_oversized_real_bytes(sessionmaker: Session, storage: MemoryStorage) -> None:
    """The signed length is not trusted alone: the stored size is read again."""
    owner = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE platform_settings SET value = '1000' WHERE key = 'media.max_image_bytes'")
        )
        await db.commit()
    try:
        media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
        assert await process_media(sessionmaker, storage, media_id) == "rejected"
        assert (await _row(sessionmaker, media_id)).rejection_reason == "too_large"
    finally:
        async with sessionmaker() as db:
            await db.execute(
                text(
                    "UPDATE platform_settings SET value = '15728640'"
                    " WHERE key = 'media.max_image_bytes'"
                )
            )
            await db.commit()


async def test_processing_idempotent(sessionmaker: Session, storage: MemoryStorage) -> None:
    """A replayed job changes nothing: same variants, no extra object, no second event."""
    owner = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    assert await process_media(sessionmaker, storage, media_id) == "ready"
    first, objects = (await _row(sessionmaker, media_id)).variants, dict(storage.objects)
    assert await process_media(sessionmaker, storage, media_id) == "ready"
    assert (await _row(sessionmaker, media_id)).variants == first
    assert storage.objects == objects
    assert len(await _events(sessionmaker, media_id)) == 1


async def test_concurrent_runs_leave_one_set_of_variants(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    outcomes = await asyncio.gather(*(process_media(sessionmaker, storage, media_id) for _ in "ab"))
    assert outcomes == ["ready", "ready"]
    row = await _row(sessionmaker, media_id)
    assert {v["key"] for v in row.variants} == _variant_keys(storage)  # the loser cleaned up
    assert len(await _events(sessionmaker, media_id)) == 1


@pytest.mark.parametrize("status", ["uploading", "ready", "rejected"])
async def test_only_processing_media_is_processed(
    sessionmaker: Session, storage: MemoryStorage, status: str
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    """A decided media only has its original deleted (a deletion that failed after the commit is
    finished by the replay); an upload not completed keeps it."""
    media_id, key = await _media(sessionmaker, storage, owner.id, _photo(), status=status)
    assert await process_media(sessionmaker, storage, media_id) == status
    assert (("originals", key) in storage.objects) == (status == "uploading")
    assert not _variant_keys(storage)


async def test_deleted_or_unknown_media_is_left_alone(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE media SET deleted_at = now() WHERE id = :id"), {"id": media_id}
        )
        await db.commit()
    assert await process_media(sessionmaker, storage, media_id) == "gone"
    assert await process_media(sessionmaker, storage, new_id()) == "gone"
    assert not _variant_keys(storage)


async def test_duplicate_of_another_sellers_image_is_flagged(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    """Same picture from another member: flagged for moderation, never refused. The member who
    sent it first is never flagged, even once someone else's copy is ready."""
    first_owner = await make_account(sessionmaker, completed=True)
    second_owner = await make_account(sessionmaker, completed=True)
    original, _ = await _media(sessionmaker, storage, first_owner.id, _photo(101))
    assert await process_media(sessionmaker, storage, original) == "ready"
    copy, _ = await _media(sessionmaker, storage, second_owner.id, _photo(101))
    again, _ = await _media(sessionmaker, storage, first_owner.id, _photo(101))
    other, _ = await _media(sessionmaker, storage, second_owner.id, _photo(103))
    cropped = Image.open(BytesIO(_photo(101))).crop((8, 6, 792, 594))  # 2 % trimmed: 3 bits away
    near, _ = await _media(sessionmaker, storage, second_owner.id, _encode(cropped))
    avatar, _ = await _media(sessionmaker, storage, second_owner.id, _photo(101), purpose="avatar")
    async with sessionmaker() as db:  # what moderation already noted is kept
        await db.execute(
            text("UPDATE media SET moderation = '{\"note\": 1}' WHERE id = :id"), {"id": near}
        )
        await db.commit()
    for media_id in (copy, again, other, near, avatar):
        assert await process_media(sessionmaker, storage, media_id) == "ready"
    assert (await _row(sessionmaker, copy)).moderation == {"duplicate_of": str(original)}
    assert (await _row(sessionmaker, near)).moderation == {
        "note": 1,
        "duplicate_of": str(original),
    }
    assert (await _row(sessionmaker, again)).moderation == {}
    assert (await _row(sessionmaker, other)).moderation == {}
    assert (await _row(sessionmaker, avatar)).moderation == {}  # only listing photos compared


async def test_only_live_listing_photos_are_references(
    sessionmaker: Session, storage: MemoryStorage
) -> None:
    first_owner = await make_account(sessionmaker, completed=True)
    second_owner = await make_account(sessionmaker, completed=True)
    original, _ = await _media(sessionmaker, storage, first_owner.id, _photo(105))
    assert await process_media(sessionmaker, storage, original) == "ready"
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE media SET deleted_at = now() WHERE id = :id"), {"id": original}
        )
        await db.commit()
    copy, _ = await _media(sessionmaker, storage, second_owner.id, _photo(105))
    assert await process_media(sessionmaker, storage, copy) == "ready"
    assert (await _row(sessionmaker, copy)).moderation == {}
    # Another member's avatar is not a listing photo: no reference either.
    avatar, _ = await _media(sessionmaker, storage, first_owner.id, _photo(106), purpose="avatar")
    listing, _ = await _media(sessionmaker, storage, second_owner.id, _photo(106))
    for media_id in (avatar, listing):
        assert await process_media(sessionmaker, storage, media_id) == "ready"
    assert (await _row(sessionmaker, listing)).moderation == {}


async def test_failed_attempts_are_retried_then_the_media_rejected(
    sessionmaker: Session,
) -> None:
    """arq retries only on Retry: a failure is retried, the last try gives up cleanly."""
    storage = FlakyStorage()
    storage.fail.add("get")
    owner = await make_account(sessionmaker, completed=True)
    media_id, key = await _media(sessionmaker, storage, owner.id, _photo())
    ctx: dict[str, Any] = {"sessionmaker": sessionmaker, "storage": storage}
    for attempt in (1, 2):
        with pytest.raises(Retry) as retry:
            await process_media_job(ctx | {"job_try": attempt}, str(media_id))
        assert retry.value.defer_score == 1000 * 2**attempt
    assert (await _row(sessionmaker, media_id)).status == "processing"
    assert await process_media_job(ctx | {"job_try": 3}, str(media_id)) == "rejected"
    row = await _row(sessionmaker, media_id)
    assert (row.status, row.rejection_reason) == ("rejected", "processing_failed")
    assert ("originals", key) not in storage.objects


async def test_failure_after_variants_leaves_nothing_public(sessionmaker: Session) -> None:
    storage = FlakyStorage()
    owner = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    storage.fail.add("put")  # the third variant upload fails
    with pytest.raises(ConnectionError):
        await process_media(sessionmaker, storage, media_id)
    assert not _variant_keys(storage)
    storage.fail.clear()

    async def no_database(*_: Any, **__: Any) -> bool:
        raise ConnectionError("database unreachable")

    original = processing._mark_ready  # pyright: ignore[reportPrivateUsage]
    processing._mark_ready = no_database  # pyright: ignore[reportPrivateUsage]
    try:
        with pytest.raises(ConnectionError):
            await process_media(sessionmaker, storage, media_id)
    finally:
        processing._mark_ready = original  # pyright: ignore[reportPrivateUsage]
    assert not _variant_keys(storage)
    assert (await _row(sessionmaker, media_id)).status == "processing"
    assert await process_media(sessionmaker, storage, media_id) == "ready"


async def test_original_deleted_by_the_replay_when_its_deletion_failed(
    sessionmaker: Session,
) -> None:
    storage = FlakyStorage()
    owner = await make_account(sessionmaker, completed=True)
    media_id, key = await _media(sessionmaker, storage, owner.id, _photo())
    storage.fail.add("delete-originals")
    with pytest.raises(ConnectionError):
        await process_media(sessionmaker, storage, media_id)
    assert (await _row(sessionmaker, media_id)).status == "ready"
    assert ("originals", key) in storage.objects
    assert await process_media(sessionmaker, storage, media_id) == "ready"
    assert ("originals", key) not in storage.objects


async def test_media_deleted_during_processing_is_not_published(sessionmaker: Session) -> None:
    storage = FlakyStorage()
    owner = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())

    async def delete_media() -> None:
        async with sessionmaker() as db:
            await db.execute(
                text("UPDATE media SET deleted_at = now() WHERE id = :id"), {"id": media_id}
            )
            await db.commit()

    storage.before_get = delete_media
    assert await process_media(sessionmaker, storage, media_id) == "gone"
    assert not _variant_keys(storage)
    assert await _events(sessionmaker, media_id) == []


async def test_rejection_loses_to_a_run_that_already_decided(sessionmaker: Session) -> None:
    storage = FlakyStorage()
    owner = await make_account(sessionmaker, completed=True)
    media_id, _ = await _media(sessionmaker, storage, owner.id, b"#!/bin/sh\n" * 50)

    async def other_run_finishes() -> None:
        async with sessionmaker() as db:
            await db.execute(
                text(
                    "UPDATE media SET status = 'ready', sha256 = :h, exif_stripped = true,"
                    ' variants = \'[{"format": "webp"}]\' WHERE id = :id'
                ),
                {"h": b"\x01" * 32, "id": media_id},
            )
            await db.commit()

    storage.before_get = other_run_finishes
    assert await process_media(sessionmaker, storage, media_id) == "ready"
    assert await _events(sessionmaker, media_id) == []


async def test_stuck_media_rejected_after_thirty_minutes(sessionmaker: Session) -> None:
    storage = FlakyStorage()
    owner = await make_account(sessionmaker, completed=True)
    stuck, key = await _media(sessionmaker, storage, owner.id, _photo())
    recent, _ = await _media(sessionmaker, storage, owner.id, _photo())
    async with sessionmaker() as db:
        await db.execute(text("SET LOCAL session_replication_role = replica"))  # no trigger
        await db.execute(
            text("UPDATE media SET updated_at = :at WHERE id = :id"),
            [{"at": T0 - timedelta(minutes=31), "id": stuck}, {"at": T0, "id": recent}],
        )
        await db.commit()
    await recover_stuck_media(sessionmaker, storage, clock=FixedClock(T0))
    row = await _row(sessionmaker, stuck)
    assert (row.status, row.rejection_reason) == ("rejected", "processing_failed")
    assert ("originals", key) not in storage.objects
    assert (await _row(sessionmaker, recent)).status == "processing"


async def test_read_is_bounded() -> None:
    storage = MemoryStorage()
    await storage.put("originals", "k", b"x" * 100, content_type="image/png")
    assert len(await storage.get("originals", "k", max_bytes=10)) == 11
    assert len(await storage.get("originals", "k")) == 100
