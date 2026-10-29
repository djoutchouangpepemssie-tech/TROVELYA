"""Favorites and price watches (P2-T08, section 11.5, plan Q43). Never commits.

A member puts in favorites, or watches the price of, someone else's listing online (404 for any
other, 409 for their own); doing it twice changes nothing, taking it back always works. The
listing's favorite count moves in the same statement as the favorite; the listing is locked
first, as the purge and the erasure do. Watching a price puts the listing in favorites, taking
the favorite back stops the watch (Q43). The price drop is only recorded in P2: the member is
told with the notifications (P3)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode, FieldError
from trovelya.core.pagination import decode_cursor, encode_cursor
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.schemas import FavoritePage
from trovelya.modules.identity.service import shown_sellers
from trovelya.modules.media.service import listing_photos

LOWEST_PRICE_MINOR = 100  # the lowest price of a listing (7.5)


async def _online_target(db: AsyncSession, member_id: UUID, listing_id: UUID) -> int:
    """The price of someone else's listing online; 404 or 409 otherwise."""
    row = await repository.favorite_target(db, listing_id)
    shown = row is not None and row.status == "active"
    if not shown or row is None or not await shown_sellers(db, [row.seller_id]):
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if row.seller_id == member_id:
        raise AppError(ErrorCode.OWN_LISTING, 409)
    return int(row.price_minor)


async def add_favorite(
    db: AsyncSession, *, member_id: UUID, listing_id: UUID, now: datetime
) -> None:
    await _online_target(db, member_id, listing_id)
    await repository.add_favorite(db, member_id, listing_id, now)


async def remove_favorite(db: AsyncSession, *, member_id: UUID, listing_id: UUID) -> None:
    await repository.remove_favorite(db, member_id, listing_id)


async def watch_price(
    db: AsyncSession, *, member_id: UUID, listing_id: UUID, target_minor: int | None, now: datetime
) -> None:
    """Q43: a target from the lowest price to below the current one; none: any drop."""
    price = await _online_target(db, member_id, listing_id)
    if target_minor is not None and not LOWEST_PRICE_MINOR <= target_minor < price:
        error = FieldError(
            field="target_minor",
            code="out_of_range",
            message="Le prix visé doit être d'au moins 1 € et sous le prix actuel",
        )
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, errors=[error])
    await repository.add_favorite(db, member_id, listing_id, now)  # Q43: watching is favoring
    await repository.set_price_watch(db, member_id, listing_id, target_minor, now)


async def unwatch_price(db: AsyncSession, *, member_id: UUID, listing_id: UUID) -> None:
    await repository.remove_price_watch(db, member_id, listing_id)


async def my_favorites(
    db: AsyncSession,
    *,
    member_id: UUID,
    available: bool,
    cursor: str | None,
    limit: int,
    media_public_url: str | None,
) -> FavoritePage:
    """The member's favorites still online (`available`), or the others, the latest first."""
    rows = await repository.my_favorites(
        db, user_id=member_id, available=available, after=decode_cursor(cursor), limit=limit + 1
    )
    page, has_more = rows[:limit], len(rows) > limit
    photos = await listing_photos.photo_variants_by_id(
        db, [m for row in page for m in row["media_ids"]], public_url=media_public_url
    )
    data: list[dict[str, Any]] = []
    for row in page:
        shown = row["shown"]  # removed, or awaiting review: neither title nor price
        data.append(
            row
            | {
                "title": row["title"] if shown else None,
                "price": {"amount_minor": row["price_minor"], "currency": row["currency"]}
                if shown
                else None,
                "cover": next((photos[m] for m in row["media_ids"] if m in photos), None),
                "price_watch": {"target_minor": row["target_minor"]} if row["watching"] else None,
            }
        )
    last = page[-1] if has_more else None
    return FavoritePage.model_validate(
        {
            "data": data,
            "next_cursor": encode_cursor(last["favorited_at"], last["id"]) if last else None,
            "has_more": has_more,
        }
    )
