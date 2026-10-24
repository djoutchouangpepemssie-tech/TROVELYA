"""The signed-in person's own resources (`/v1/me/*`)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from trovelya.core.errors import AppError, ErrorCode, problem_response
from trovelya.modules.identity.schemas import (
    CompleteProfile,
    MeOut,
    ProfilePatch,
    SessionList,
    SessionOut,
    UsernameSuggestion,
)
from trovelya.modules.identity.service import (
    CurrentUser,
    SessionPolicy,
    clear_session_cookie,
    current_user,
    get_clock,
    get_session_policy,
    list_sessions,
    profile,
    revoke_other_sessions,
    revoke_session,
)
from trovelya.modules.identity.service.auth import Uow, completed_user
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


@router.get("", operation_id="me_get")
async def get_me(request: Request, db: Uow, user: Me, clock: ClockDep) -> MeOut:
    data = await profile.me(db, user=user, flags=request.app.state.flags, clock=clock)
    return MeOut.model_validate(data)


@router.get("/username-suggestion", operation_id="me_username_suggestion")
async def get_username_suggestion(db: Uow, user: Me) -> UsernameSuggestion:
    return UsernameSuggestion(username=await profile.suggest_username(db, user=user))


@router.post(
    "/complete-profile",
    operation_id="me_complete_profile",
    response_model=MeOut,
    responses={400: {"description": "too_young: the account has been erased"}},
)
async def post_complete_profile(
    body: CompleteProfile, request: Request, db: Uow, user: Me, clock: ClockDep
) -> MeOut | JSONResponse:
    """First step of /bienvenue (Q11). Under the minimum age nothing is kept: the account is
    erased, the session cookie cleared, and the answer is `400 too_young`."""
    completion = await profile.complete_profile(
        db,
        user=user,
        username=body.username,
        display_name=body.display_name,
        birth_year=body.birth_year,
        terms_version=body.terms_version,
        clock=clock,
    )
    if not completion.accepted:
        # Not raised: the erasure must commit with this request.
        response = problem_response(request, ErrorCode.TOO_YOUNG, 400)
        clear_session_cookie(response)
        return response
    completed = CurrentUser(
        id=user.id,
        session_id=user.session_id,
        kind=user.kind,
        mfa_at=user.mfa_at,
        is_staff=user.is_staff,
        profile_completed=True,
    )
    data = await profile.me(db, user=completed, flags=request.app.state.flags, clock=clock)
    return MeOut.model_validate(data)


@router.patch("", operation_id="me_update")
async def patch_me(
    body: ProfilePatch,
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(completed_user)],
    clock: ClockDep,
) -> MeOut:
    """Change the username, display name, bio or language. `If-Match: <version>` required."""
    await profile.update_profile(
        db, user=user, if_match=request.headers.get("if-match"), changes=body.changes()
    )
    data = await profile.me(db, user=user, flags=request.app.state.flags, clock=clock)
    return MeOut.model_validate(data)
