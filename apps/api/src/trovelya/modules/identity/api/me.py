"""The signed-in person's own resources (`/v1/me/*`)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from trovelya.core.client_ip import client_ip
from trovelya.core.csrf import require_csrf
from trovelya.core.errors import AppError, ErrorCode, problem_response
from trovelya.modules.identity.schemas import (
    BlockedMember,
    BlockList,
    CompleteProfile,
    ConsentIn,
    ConsentOut,
    ConsentState,
    DataExportAccepted,
    DataRequestList,
    DataRequestOut,
    EmailChangeRequest,
    ErasureAccepted,
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
    consents,
    current_user,
    gdpr,
    get_clock,
    get_session_policy,
    limit_magic_link_requests,
    list_sessions,
    optional_user,
    profile,
    revoke_other_sessions,
    revoke_session,
    social,
)
from trovelya.modules.identity.service.auth import Uow, completed_user, recent_mfa_user
from trovelya.modules.identity.service.email_change import request_email_change
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/me", tags=["me"])

Me = Annotated[CurrentUser, Depends(current_user)]
MaybeMe = Annotated[CurrentUser | None, Depends(optional_user)]
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


@router.post("/email", operation_id="me_email_change", status_code=status.HTTP_202_ACCEPTED)
async def post_email_change(
    body: EmailChangeRequest,
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(recent_mfa_user)],
    clock: ClockDep,
) -> dict[str, str]:
    """Send a confirmation link to the new address. Same answer whatever the address."""
    settings = request.app.state.settings
    ip = client_ip(request.scope, proxy_secret=settings.proxy_shared_secret.get_secret_value())
    new_email = body.new_email.strip().lower()
    await limit_magic_link_requests(
        request.app.state.redis,
        email=new_email,
        ip=ip,
        secret=settings.secret_key.get_secret_value(),
    )
    await request_email_change(
        db,
        request.app.state.queue,
        user=user,
        new_email=new_email,
        ip=ip,
        settings=settings,
        clock=clock,
    )
    return {}


async def _consent_state(
    db: Uow, *, user: CurrentUser | None, anonymous_id: str | None
) -> ConsentState:
    rows = await consents.latest(db, user_id=user.id if user else None, anonymous_id=anonymous_id)
    return ConsentState(
        active_purposes=await consents.active_purposes(db),
        consents=[ConsentOut.model_validate(row, from_attributes=True) for row in rows],
    )


@router.get("/consents", operation_id="me_consents_get")
async def get_consents(request: Request, db: Uow, user: MaybeMe) -> ConsentState:
    """Signed in or not: an anonymous browser is recognised by `__Host-trv_anon`."""
    anonymous_id = consents.valid_anonymous_id(request.cookies.get(consents.ANON_COOKIE))
    return await _consent_state(db, user=user, anonymous_id=anonymous_id)


@router.post(
    "/consents",
    operation_id="me_consents_record",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def post_consent(
    body: ConsentIn,
    request: Request,
    response: Response,
    db: Uow,
    user: MaybeMe,
    clock: ClockDep,
) -> ConsentState:
    """Records a choice (granting or withdrawing) and answers the new state. An anonymous
    browser without a valid `__Host-trv_anon` receives one (13 months)."""
    anonymous_id = consents.valid_anonymous_id(request.cookies.get(consents.ANON_COOKIE))
    if user is None and anonymous_id is None:
        anonymous_id = consents.new_anonymous_id()
        consents.set_anonymous_cookie(response, anonymous_id)
    await consents.record(
        db,
        user_id=user.id if user else None,
        anonymous_id=anonymous_id,
        purpose=body.purpose,
        granted=body.granted,
        policy_version=body.policy_version,
        clock=clock,
    )
    return await _consent_state(db, user=user, anonymous_id=anonymous_id)


def _audit_context(request: Request) -> tuple[str | None, str | None]:
    secret = request.app.state.settings.proxy_shared_secret.get_secret_value()
    return client_ip(request.scope, proxy_secret=secret), request.headers.get("user-agent")


@router.post(
    "/data-export",
    operation_id="me_data_export_request",
    status_code=status.HTTP_202_ACCEPTED,
    responses={403: {"description": "step_up_required"}},
)
async def post_data_export(
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(recent_mfa_user)],
    clock: ClockDep,
) -> DataExportAccepted:
    """GDPR export (ADR-0016): built by the worker, announced by e-mail. A request still in
    progress is answered again instead of starting a second one."""
    ip, user_agent = _audit_context(request)
    request_id = await gdpr.request_export(
        db,
        user_id=user.id,
        queue=request.app.state.queue,
        clock=clock,
        ip=ip,
        user_agent=user_agent,
    )
    return DataExportAccepted(request_id=request_id)


@router.get("/data-requests", operation_id="me_data_requests_list")
async def get_data_requests(db: Uow, user: Me) -> DataRequestList:
    rows = await gdpr.list_requests(db, user.id)
    return DataRequestList(
        data=[DataRequestOut.model_validate(row, from_attributes=True) for row in rows]
    )


@router.get(
    "/data-export/{request_id}/download",
    operation_id="me_data_export_download",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "The export archive"},
        403: {"description": "step_up_required"},
        404: {"description": "Unknown, someone else's, not ready or expired"},
    },
)
async def get_data_export(
    request_id: UUID,
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(recent_mfa_user)],
    clock: ClockDep,
) -> Response:
    ip, user_agent = _audit_context(request)
    archive = await gdpr.download_export(
        db,
        user_id=user.id,
        request_id=request_id,
        settings=request.app.state.settings,
        clock=clock,
        ip=ip,
        user_agent=user_agent,
    )
    filename = f"trovelya-export-{clock.now().date().isoformat()}.zip"
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "content-disposition": f'attachment; filename="{filename}"',
            "cache-control": "no-store",
        },
    )


@router.post(
    "/erasure",
    operation_id="me_erasure_request",
    status_code=status.HTTP_202_ACCEPTED,
    responses={403: {"description": "step_up_required"}},
)
async def post_erasure(
    request: Request,
    response: Response,
    db: Uow,
    user: Annotated[CurrentUser, Depends(recent_mfa_user)],
    clock: ClockDep,
) -> ErasureAccepted:
    """Account erasure (Q10): every session is revoked (this one too) and the public profile
    hidden at once; the account is erased after the grace period unless the person signs in
    again and cancels."""
    ip, user_agent = _audit_context(request)
    erase_at = await gdpr.request_erasure(
        db,
        user_id=user.id,
        queue=request.app.state.queue,
        settings=request.app.state.settings,
        clock=clock,
        ip=ip,
        user_agent=user_agent,
    )
    clear_session_cookie(response)
    return ErasureAccepted(erase_at=erase_at)


@router.post(
    "/erasure/cancel",
    operation_id="me_erasure_cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "no_erasure_pending"}},
)
async def post_erasure_cancel(request: Request, db: Uow, user: Me, clock: ClockDep) -> None:
    ip, user_agent = _audit_context(request)
    await gdpr.cancel_erasure(db, user_id=user.id, clock=clock, ip=ip, user_agent=user_agent)


@router.get("/blocks", operation_id="me_blocks_list")
async def get_blocks(db: Uow, user: Annotated[CurrentUser, Depends(completed_user)]) -> BlockList:
    rows = await social.blocks(db, user.id)
    return BlockList(data=[BlockedMember.model_validate(r, from_attributes=True) for r in rows])
