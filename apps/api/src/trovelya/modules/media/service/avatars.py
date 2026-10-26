"""Avatars (P2-T02c1, end of gap E13 of P1): what the identity module needs of media."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.media import repository


async def check_avatar(db: AsyncSession, *, owner_id: UUID, media_id: UUID) -> None:
    """A member's avatar is one of their own photos, sent as an avatar and processed:
    404 for anyone else's (or none), 422 for another purpose or a refused file, 409 while
    still being processed."""
    row = await repository.owned_media(db, media_id, owner_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if row.purpose != "avatar":
        raise AppError(ErrorCode.MEDIA_NOT_AVATAR, 422)
    if row.status == "rejected":
        raise AppError(ErrorCode.MEDIA_REJECTED, 422)
    if row.status != "ready":
        raise AppError(ErrorCode.MEDIA_NOT_READY, 409)


async def discard(db: AsyncSession, media_id: UUID, *, now: datetime) -> None:
    """A replaced or removed avatar is deleted; the purge removes its files."""
    await repository.mark_deleted(db, media_id, now)


async def avatar_variants(
    db: AsyncSession, media_id: UUID | None, *, public_url: str | None
) -> list[dict[str, Any]] | None:
    """The avatar's public variants (format, width, height, url), or None when there is none."""
    if media_id is None:
        return None
    variants = await repository.ready_variants(db, media_id)
    if variants is None:
        return None
    base = (public_url or "").rstrip("/")
    return [
        {
            "format": v["format"],
            "width": v["width"],
            "height": v["height"],
            "url": f"{base}/{v['key']}",
        }
        for v in variants
    ]
