"""Photos a seller attaches to a listing (plan P2 E16, P2-T03b2b1).

Each one must be the seller's own photo, sent for a listing and processed. It is locked
`FOR SHARE` until the listing's transaction ends, so the purge (which takes `FOR NO KEY UPDATE`)
never deletes a photo being attached.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.media import repository


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


async def photo_variants(
    db: AsyncSession, media_ids: Sequence[UUID], *, public_url: str | None
) -> list[list[dict[str, Any]]]:
    """The public variants of each photo, in the order given; a photo no longer ready (deleted,
    removed by moderation) is left out."""
    base = (public_url or "").rstrip("/")
    photos: list[list[dict[str, Any]]] = []
    for media_id in media_ids:
        variants = await repository.ready_variants(db, media_id)
        if variants:
            photos.append(
                [
                    {
                        "format": v["format"],
                        "width": v["width"],
                        "height": v["height"],
                        "url": f"{base}/{v['key']}",
                    }
                    for v in variants
                ]
            )
    return photos
