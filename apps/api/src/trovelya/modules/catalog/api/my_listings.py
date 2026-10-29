"""The signed-in seller's listings (`/v1/me/listings`, section 11.5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from trovelya.core.db import Uow
from trovelya.core.pagination import DEFAULT_LIMIT, Cursor, Limit
from trovelya.modules.catalog.models import ListingStatus
from trovelya.modules.catalog.schemas import ListingSummaryPage
from trovelya.modules.catalog.service import reading
from trovelya.modules.identity.service import CurrentUser
from trovelya.modules.identity.service.auth import completed_user

router = APIRouter(prefix="/v1/me", tags=["catalog"])


@router.get("/listings", operation_id="me_listings")
async def get_my_listings(
    request: Request,
    db: Uow,
    me: Annotated[CurrentUser, Depends(completed_user)],
    status: ListingStatus | None = None,
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> ListingSummaryPage:
    """The caller's listings, newest first, any status but deleted ones; `status` filters."""
    return await reading.seller_listings(
        db,
        seller_id=me.id,
        status=status.value if status else None,
        cursor=cursor,
        limit=limit,
        media_public_url=request.app.state.settings.media_public_url,
    )
