"""Favorites and price watches (P2-T08, section 11.5, plan Q43)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from trovelya.core.db import Uow
from trovelya.core.pagination import DEFAULT_LIMIT, Cursor, Limit
from trovelya.modules.catalog.schemas import FavoritePage, PriceWatchIn
from trovelya.modules.catalog.service import favorites
from trovelya.modules.identity.service import CurrentUser, get_clock
from trovelya.modules.identity.service.auth import completed_user
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1", tags=["catalog"])

Member = Annotated[CurrentUser, Depends(completed_user)]
ClockDep = Annotated[Clock, Depends(get_clock)]
_TARGET_ERRORS: dict[int | str, dict[str, str]] = {
    404: {"description": "No such listing online"},
    409: {"description": "The caller's own listing"},
}
NO_CONTENT = status.HTTP_204_NO_CONTENT


@router.post(
    "/listings/{listing_id}/favorite",
    operation_id="favorite_add",
    status_code=NO_CONTENT,
    responses=_TARGET_ERRORS,
)
async def add_favorite(listing_id: UUID, db: Uow, me: Member, clock: ClockDep) -> Response:
    """Idempotent: a listing already in favorites stays once."""
    await favorites.add_favorite(db, member_id=me.id, listing_id=listing_id, now=clock.now())
    return Response(status_code=NO_CONTENT)


@router.delete(
    "/listings/{listing_id}/favorite", operation_id="favorite_remove", status_code=NO_CONTENT
)
async def remove_favorite(listing_id: UUID, db: Uow, me: Member) -> Response:
    """Always possible, the listing online or not; idempotent."""
    await favorites.remove_favorite(db, member_id=me.id, listing_id=listing_id)
    return Response(status_code=NO_CONTENT)


@router.post(
    "/listings/{listing_id}/price-watch",
    operation_id="price_watch_set",
    status_code=NO_CONTENT,
    responses=_TARGET_ERRORS | {422: {"description": "Target below 1 € or not below the price"}},
)
async def watch_price(
    listing_id: UUID, body: PriceWatchIn, db: Uow, me: Member, clock: ClockDep
) -> Response:
    """Watches the price, to a target or any drop; sent again, the target is replaced."""
    await favorites.watch_price(
        db, member_id=me.id, listing_id=listing_id, target_minor=body.target_minor, now=clock.now()
    )
    return Response(status_code=NO_CONTENT)


@router.delete(
    "/listings/{listing_id}/price-watch", operation_id="price_watch_remove", status_code=NO_CONTENT
)
async def unwatch_price(listing_id: UUID, db: Uow, me: Member) -> Response:
    await favorites.unwatch_price(db, member_id=me.id, listing_id=listing_id)
    return Response(status_code=NO_CONTENT)


@router.get("/me/favorites", operation_id="me_favorites")
async def my_favorites(
    request: Request,
    db: Uow,
    me: Member,
    available: bool = True,
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> FavoritePage:
    """The caller's favorites still online (`available`, the default), or the others."""
    return await favorites.my_favorites(
        db,
        member_id=me.id,
        available=available,
        cursor=cursor,
        limit=limit,
        media_public_url=request.app.state.settings.media_public_url,
    )
