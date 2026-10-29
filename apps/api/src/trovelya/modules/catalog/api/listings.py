"""Listings of the signed-in seller (`/v1/listings`, section 11.5)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from trovelya.core.db import Uow
from trovelya.core.idempotency import require_idempotency_key
from trovelya.core.preconditions import if_match_version
from trovelya.modules.catalog.schemas import ListingDraftIn, ListingDraftPatch, ListingOut
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
        409: {"description": "Photo processing or in another listing: retry with a new key"},
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


@router.patch(
    "/{listing_id}",
    operation_id="listing_update",
    responses={
        404: {"description": "Not the caller's listing"},
        409: {"description": "No longer a draft, or a photo in another listing or processing"},
        412: {"description": "If-Match is not the listing's version"},
        422: {"description": "The draft as it becomes breaks a rule of its category"},
        428: {"description": "If-Match missing"},
    },
)
async def patch_listing(
    listing_id: UUID,
    body: ListingDraftPatch,
    request: Request,
    db: Uow,
    me: Member,
    clock: Annotated[Clock, Depends(get_clock)],
) -> ListingOut:
    """Change a draft. `If-Match: <version>` required."""
    version = if_match_version(request.headers.get("if-match"))
    verticals = await request.app.state.flags.is_enabled("verticals")
    return await listings.update_draft(
        db,
        seller_id=me.id,
        listing_id=listing_id,
        version=version,
        patch=body,
        verticals=verticals,
        clock=clock,
    )
