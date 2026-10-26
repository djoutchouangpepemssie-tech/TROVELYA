"""The worker's `process_media` (P2-T02b2, ADR-0019): `processing` → `ready` with clean
variants in the public bucket, or `rejected` with a reason; the original never outlives it."""

import asyncio
import random
from io import BytesIO
from typing import Any
from uuid import UUID

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import make_account
from trovelya.modules.media.adapters.storage import MemoryStorage, new_storage_key
from trovelya.modules.media.service.processing import process_media
from trovelya.modules.media.tasks import process_media_job
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


async def _media(
    sessionmaker: Session,
    storage: MemoryStorage,
    owner_id: UUID,
    data: bytes | None,
    mime: str = "image/jpeg",
    status: str = "processing",
) -> tuple[UUID, str]:
    """A media row as `complete` leaves it, with its original in storage (None: never sent)."""
    media_id, key = new_id(), new_storage_key()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
                " status)"
                " VALUES (:id, :owner, 'image', 'listing', :key, :mime, :bytes, 'processing')"
            ),
            {
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
    ctx = {"sessionmaker": sessionmaker, "storage": storage}
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
    media_id, key = await _media(sessionmaker, storage, owner.id, _photo(), status=status)
    assert await process_media(sessionmaker, storage, media_id) == status
    assert ("originals", key) in storage.objects and not _variant_keys(storage)


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
    for media_id in (copy, again, other):
        assert await process_media(sessionmaker, storage, media_id) == "ready"
    assert (await _row(sessionmaker, copy)).moderation == {"duplicate_of": str(original)}
    assert (await _row(sessionmaker, again)).moderation == {}
    assert (await _row(sessionmaker, other)).moderation == {}
