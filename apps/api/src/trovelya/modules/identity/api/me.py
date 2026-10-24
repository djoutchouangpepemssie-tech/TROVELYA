"""The signed-in person's own resources (`/v1/me/*`)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.schemas import SessionList, SessionOut
from trovelya.modules.identity.service import (
    CurrentUser,
    SessionPolicy,
    current_user,
    get_clock,
    get_session_policy,
    list_sessions,
    revoke_other_sessions,
    revoke_session,
)
from trovelya.modules.identity.service.auth import Uow
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/me", tags=["me"])

Me = Annotated[CurrentUser, Depends(current_user)]
ClockDep = Annotated[Clock, Depends(get_clock)]


@router.get("/sessions", operation_id="me_sessions_list")
async def get_sessions(
    db: Uow,
    user: Me,
    clock: ClockDep,
    policy: Annotated[SessionPolicy, Depends(get_session_policy)],
) -> SessionList:
    sessions = await list_sessions(db, current=user, policy=policy, clock=clock)
    return SessionList(data=[SessionOut.model_validate(s, from_attributes=True) for s in sessions])


@router.delete(
    "/sessions/{session_id}",
    operation_id="me_sessions_revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(session_id: UUID, db: Uow, user: Me, clock: ClockDep) -> None:
    if not await revoke_session(db, user_id=user.id, session_id=session_id, clock=clock):
        raise AppError(ErrorCode.NOT_FOUND, 404)


@router.delete(
    "/sessions", operation_id="me_sessions_revoke_others", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_other_sessions(db: Uow, user: Me, clock: ClockDep) -> None:
    """Sign out everywhere else; the current session stays open."""
    await revoke_other_sessions(db, current=user, clock=clock)
