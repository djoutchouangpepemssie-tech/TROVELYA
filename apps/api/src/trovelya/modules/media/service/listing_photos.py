"""Photos a seller attaches to a listing (plan P2 E16, P2-T03b2b1).

Each one must be the seller's own photo, sent for a listing and processed. It is locked
`FOR SHARE` until the listing's transaction ends, so the purge (which takes `FOR NO KEY UPDATE`)
never deletes a photo being attached.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.media import repository
from trovelya.modules.media.adapters.classifier import valid_scores


async def check_listing_photos(
    db: AsyncSession, *, owner_id: UUID, media_ids: Sequence[UUID]
) -> None:
    """404 for anyone else's photo (or none), 422 for another purpose or a refused file, 409
    while one is still being processed."""
    for media_id in media_ids:
        row = await repository.owned_media(db, media_id, owner_id, lock=True)
        if row is None:
            raise AppError(ErrorCode.NOT_FOUND, 404)
        if row.purpose != "listing":
            raise AppError(ErrorCode.MEDIA_NOT_LISTING, 422)
        if row.status == "rejected":
            raise AppError(ErrorCode.MEDIA_REJECTED, 422)
        if row.status != "ready":
            raise AppError(ErrorCode.MEDIA_NOT_READY, 409)


async def photos_taken_off(db: AsyncSession, media_ids: Sequence[UUID], *, at: datetime) -> None:
    """Photos a seller took off a draft: the purge gives them 24 hours from `at` to go back on
    a listing (`mark_for_purge`)."""
    if media_ids:
        await repository.mark_detached(db, media_ids, at)


async def discard_photos(db: AsyncSession, media_ids: Sequence[UUID], *, now: datetime) -> None:
    """The photos of a listing being purged are deleted; the media purge removes their files
    at its next run (ADR-0019)."""
    for media_id in media_ids:
        await repository.mark_deleted(db, media_id, now)


def _public(variants: list[dict[str, Any]], base: str) -> list[dict[str, Any]]:
    return [
        {
            "format": v["format"],
            "width": v["width"],
            "height": v["height"],
            "url": f"{base}/{v['key']}",
        }
        for v in variants
    ]


async def photo_variants_by_id(
    db: AsyncSession, media_ids: Sequence[UUID], *, public_url: str | None
) -> dict[UUID, list[dict[str, Any]]]:
    """The public variants of each photo still ready, by id, read in one query."""
    base = (public_url or "").rstrip("/")
    found = await repository.ready_variants_of(db, media_ids)
    return {media_id: _public(variants, base) for media_id, variants in found.items() if variants}


async def photo_variants(
    db: AsyncSession, media_ids: Sequence[UUID], *, public_url: str | None
) -> list[list[dict[str, Any]]]:
    """The public variants of each photo, in the order given, read in one query; a photo no
    longer ready (deleted, removed by moderation) is left out."""
    found = await photo_variants_by_id(db, media_ids, public_url=public_url)
    return [found[media_id] for media_id in media_ids if media_id in found]


async def photo_moderation(db: AsyncSession, media_ids: Sequence[UUID]) -> list[dict[str, Any]]:
    """What the moderation of a listing reads of its photos (P2-T05b2), in the order given:
    `scores` (the four categories, valid) or None when unclassified, and `duplicate_of`
    another member's photo."""
    found = await repository.ready_moderation_of(db, media_ids)
    photos: list[dict[str, Any]] = []
    for media_id in media_ids:
        if (moderation := found.get(media_id)) is None:
            continue
        classification: Any = moderation.get("classification")
        scores: Any = (
            cast(dict[str, Any], classification).get("scores")
            if isinstance(classification, dict)
            else None
        )
        photos.append(
            {"scores": valid_scores(scores), "duplicate_of": moderation.get("duplicate_of")}
        )
    return photos
