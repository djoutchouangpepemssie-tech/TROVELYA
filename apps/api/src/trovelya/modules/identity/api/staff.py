"""Staff back office (`/v1/staff/*`): staff accounts in an admin session only (3.1)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from trovelya.modules.identity.schemas import (
    ApprovalList,
    ApprovalOut,
    ApprovalOutcomeOut,
    StaffRoleRequest,
)
from trovelya.modules.identity.service import access, get_clock
from trovelya.modules.identity.service.auth import Uow
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/staff", tags=["staff"])

ClockDep = Annotated[Clock, Depends(get_clock)]
ManageStaffRoles = Annotated[
    access.Authorised, Depends(access.require_permission("staff_roles.manage"))
]


@router.get("/approvals", operation_id="staff_approvals_list")
async def get_approvals(db: Uow, staff: access.StaffUser, clock: ClockDep) -> ApprovalList:
    """Pending requests this person could decide (they hold the permission), theirs included."""
    rows = await access.pending_for(db, viewer=staff.id, clock=clock)
    return ApprovalList(data=[ApprovalOut.model_validate(r, from_attributes=True) for r in rows])


@router.post(
    "/approvals/{approval_id}/approve",
    operation_id="staff_approvals_approve",
    responses={409: {"description": "approval_not_pending or approval_expired"}},
)
async def post_approve(
    approval_id: UUID, db: Uow, staff: access.StaffUser, clock: ClockDep
) -> ApprovalOutcomeOut:
    outcome = await access.decide(
        db, request_id=approval_id, decided_by=staff.id, approve=True, clock=clock
    )
    return ApprovalOutcomeOut(approval_id=outcome.approval_id, status="approved")


@router.post(
    "/approvals/{approval_id}/reject",
    operation_id="staff_approvals_reject",
    responses={409: {"description": "approval_not_pending or approval_expired"}},
)
async def post_reject(
    approval_id: UUID, db: Uow, staff: access.StaffUser, clock: ClockDep
) -> ApprovalOutcomeOut:
    outcome = await access.decide(
        db, request_id=approval_id, decided_by=staff.id, approve=False, clock=clock
    )
    return ApprovalOutcomeOut(approval_id=outcome.approval_id, status="rejected")


@router.post(
    "/roles/requests",
    operation_id="staff_roles_request",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"model": ApprovalOutcomeOut, "description": "Done at once"}},
    response_model=ApprovalOutcomeOut,
)
async def post_role_request(
    body: StaffRoleRequest, db: Uow, authorised: ManageStaffRoles, clock: ClockDep
) -> ApprovalOutcomeOut | JSONResponse:
    """Grant or revoke a staff role on a staff account (`staff_roles.manage`, 🔒 dual approval
    for the super-administrator: 202 and a pending request)."""
    await access.ensure_staff_account(db, body.user_id)
    outcome = await access.perform(
        db,
        authorised=authorised,
        permission_key="staff_roles.manage",
        payload={"user_id": str(body.user_id), "role_key": body.role_key, "grant": body.grant},
        reason=body.reason,
        clock=clock,
    )
    result = ApprovalOutcomeOut(approval_id=outcome.approval_id, status=outcome.status)
    if outcome.status == "done":
        return JSONResponse(result.model_dump(mode="json"), status_code=200)
    return result
