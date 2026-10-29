"""Staff decisions on listings (`/v1/staff/*`, P2-T05c1, plan Q16, E9), each one audited."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from trovelya.core.db import Uow
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.catalog.schemas import (
    ReviewQueue,
    StaffDecisionIn,
    StaffDecisionOut,
)
from trovelya.modules.catalog.service import review
from trovelya.modules.identity.service import access, get_clock
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/staff", tags=["staff"])

ClockDep = Annotated[Clock, Depends(get_clock)]
Reviewer = Annotated[access.Authorised, Depends(access.require_permission("moderation.review"))]
Remover = Annotated[access.Authorised, Depends(access.require_permission("listing.remove_any"))]


def _direct(staff: access.Authorised) -> UUID:
    """No dual approval for the moderation yet: a role granting it only with one is refused
    rather than deciding alone."""
    if staff.grant.requires_approval:
        raise AppError(ErrorCode.FORBIDDEN, 403)
    return staff.user.id


_DECISION_ERRORS: dict[int | str, dict[str, str]] = {
    403: {"description": "Not a staff session with the permission, or the reviewer's own"},
    404: {"description": "No such listing"},
    409: {"description": "Not in the status the decision applies to, or no longer publishable"},
}


@router.get("/moderation/listings", operation_id="staff_review_queue")
async def get_review_queue(
    request: Request, db: Uow, _: Reviewer, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> ReviewQueue:
    """The listings awaiting moderation, the longest waiting first."""
    items = await review.queue(
        db, public_url=request.app.state.settings.media_public_url, limit=limit
    )
    return ReviewQueue.model_validate({"items": items})


@router.post(
    "/moderation/listings/{listing_id}/approve",
    operation_id="staff_review_approve",
    responses=_DECISION_ERRORS,
)
async def approve_listing(
    listing_id: UUID, db: Uow, staff: Reviewer, clock: ClockDep
) -> StaffDecisionOut:
    """The listing goes online for `listings.expiry_days` days."""
    status = await review.approve(db, listing_id=listing_id, staff_id=_direct(staff), clock=clock)
    return StaffDecisionOut.model_validate({"id": listing_id, "status": status})


@router.post(
    "/moderation/listings/{listing_id}/reject",
    operation_id="staff_review_reject",
    responses=_DECISION_ERRORS | {422: {"description": "Reason off the list, or unexplained"}},
)
async def reject_listing(
    listing_id: UUID, body: StaffDecisionIn, db: Uow, staff: Reviewer, clock: ClockDep
) -> StaffDecisionOut:
    """The listing is removed with its reason; its photos leave storage (Q6)."""
    status = await review.reject(
        db,
        listing_id=listing_id,
        staff_id=_direct(staff),
        reason_code=body.reason_code,
        reason_text=body.reason_text,
        clock=clock,
    )
    return StaffDecisionOut.model_validate({"id": listing_id, "status": status})


@router.post(
    "/listings/{listing_id}/remove",
    operation_id="staff_listing_remove",
    responses=_DECISION_ERRORS | {422: {"description": "Reason off the list, or unexplained"}},
)
async def remove_listing(
    listing_id: UUID, body: StaffDecisionIn, db: Uow, staff: Remover, clock: ClockDep
) -> StaffDecisionOut:
    """An active listing is taken down with its reason; its photos leave storage (Q6)."""
    status = await review.reject(
        db,
        listing_id=listing_id,
        staff_id=_direct(staff),
        reason_code=body.reason_code,
        reason_text=body.reason_text,
        clock=clock,
        remove=True,
    )
    return StaffDecisionOut.model_validate({"id": listing_id, "status": status})
