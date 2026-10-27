"""Listings of the signed-in seller (`/v1/listings`, section 11.5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from trovelya.core.db import Uow
from trovelya.core.idempotency import require_idempotency_key
from trovelya.modules.catalog.schemas import ListingDraftIn, ListingOut
from trovelya.modules.catalog.service import listings
from trovelya.modules.identity.service import CurrentUser, get_clock
from trovelya.modules.identity.service.auth import completed_user
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/listings", tags=["catalog"])

Member = Annotated[CurrentUser, Depends(completed_user)]


@router.post(
    "",
    operation_id="listing_create",
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "A photo that is not the caller's"},
        409: {"description": "A photo still processed, or already in another listing"},
        422: {"description": "Category, condition, brand, attributes, photos or place refused"},
    },
)
async def post_listing(
    body: ListingDraftIn,
    request: Request,
    db: Uow,
    me: Member,
    # After the member: an anonymous caller gets 401, not a 400 about the key.
    _key: Annotated[str, Depends(require_idempotency_key)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ListingOut:
    """A new draft. `Idempotency-Key` required: a retry never makes a second listing."""
    verticals = await request.app.state.flags.is_enabled("verticals")
    return await listings.create_draft(
        db, seller_id=me.id, body=body, verticals=verticals, clock=clock
    )
