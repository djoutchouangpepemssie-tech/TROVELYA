"""Listings of the signed-in seller (`/v1/listings`, section 11.5)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from trovelya.core.db import Uow
from trovelya.core.idempotency import require_idempotency_key
from trovelya.core.preconditions import if_match_version
from trovelya.modules.catalog.schemas import (
    ListingDraftIn,
    ListingDraftPatch,
    ListingOut,
    ListingPage,
)
from trovelya.modules.catalog.service import listings, publishing, reading
from trovelya.modules.identity.service import CurrentUser, get_clock
from trovelya.modules.identity.service.auth import completed_user, optional_user
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/listings", tags=["catalog"])

Member = Annotated[CurrentUser, Depends(completed_user)]
MaybeMember = Annotated[CurrentUser | None, Depends(optional_user)]


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


@router.get(
    "/{listing_id}",
    operation_id="listing_get",
    responses={404: {"description": "Unknown, deleted, or not active and not the caller's"}},
)
async def get_listing(
    listing_id: UUID, request: Request, response: Response, db: Uow, me: MaybeMember
) -> ListingPage:
    """The listing page: anybody for an active listing, its seller only otherwise. Never kept
    by a shared cache: the answer depends on who asks (a draft, a distance)."""
    response.headers["Cache-Control"] = "private, no-store"
    return await reading.listing_page(
        db,
        listing_id=listing_id,
        viewer_id=me.id if me else None,
        media_public_url=request.app.state.settings.media_public_url,
    )


@router.post(
    "/{listing_id}/publish",
    operation_id="listing_publish",
    responses={
        403: {"description": "Profile incomplete, under 18, or erasure in progress (Q1)"},
        404: {"description": "Not the caller's listing"},
        409: {"description": "Not a draft"},
        422: {"description": "No ready photo"},
        429: {"description": "50 listings put online over 24 hours; see Retry-After"},
    },
)
async def publish_listing(
    listing_id: UUID,
    request: Request,
    db: Uow,
    me: Member,
    clock: Annotated[Clock, Depends(get_clock)],
) -> ListingOut:
    """A draft goes online for `listings.expiry_days` (120) days."""
    gate: publishing.ModerationGate = request.app.state.moderation_gate
    return await publishing.publish(
        db, seller_id=me.id, listing_id=listing_id, gate=gate, clock=clock
    )


@router.post(
    "/{listing_id}/withdraw",
    operation_id="listing_withdraw",
    responses={
        404: {"description": "Not the caller's listing"},
        409: {"description": "Not active"},
    },
)
async def withdraw_listing(
    listing_id: UUID,
    db: Uow,
    me: Member,
    clock: Annotated[Clock, Depends(get_clock)],
) -> ListingOut:
    """Take an active listing out of the shop window."""
    return await publishing.withdraw(db, seller_id=me.id, listing_id=listing_id, clock=clock)


@router.post(
    "/{listing_id}/renew",
    operation_id="listing_renew",
    responses={
        403: {"description": "Profile incomplete, under 18, or erasure in progress (Q1)"},
        404: {"description": "Not the caller's listing"},
        409: {"description": "Neither expired nor withdrawn"},
        422: {"description": "No ready photo"},
        429: {"description": "50 listings put online over 24 hours; see Retry-After"},
    },
)
async def renew_listing(
    listing_id: UUID,
    db: Uow,
    me: Member,
    clock: Annotated[Clock, Depends(get_clock)],
) -> ListingOut:
    """Back online for 120 days: an expired listing is renewed, a withdrawn one republished."""
    return await publishing.renew(db, seller_id=me.id, listing_id=listing_id, clock=clock)
