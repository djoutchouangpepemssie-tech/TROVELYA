"""Step-up: `/v1/auth/step-up` (section 13.2). Signed-in users only.

On success the session is rotated: the answer carries a new session cookie.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from trovelya.core.client_ip import client_country, client_ip
from trovelya.core.config import Settings
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.schemas import StepUpRequest, StepUpVerify
from trovelya.modules.identity.service import (
    CurrentUser,
    IssuedSession,
    SessionPolicy,
    get_clock,
    get_session_policy,
    limit_magic_link_requests,
    set_session_cookie,
)
from trovelya.modules.identity.service.auth import Uow, completed_user
from trovelya.modules.identity.service.passkeys import RelyingParty, step_up_options
from trovelya.modules.identity.service.step_up import (
    request_step_up_link,
    step_up_with_passkey,
    verify_step_up_link,
)
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/auth/step-up", tags=["auth"])

Me = Annotated[CurrentUser, Depends(completed_user)]
ClockDep = Annotated[Clock, Depends(get_clock)]
PolicyDep = Annotated[SessionPolicy, Depends(get_session_policy)]


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _secret(request: Request) -> str:
    return _settings(request).proxy_shared_secret.get_secret_value()


async def _require_passkeys(request: Request) -> None:
    if not await request.app.state.flags.is_enabled("auth.passkeys"):
        raise AppError(ErrorCode.NOT_FOUND, 404)


def _rotated(response: Response, issued: IssuedSession, clock: Clock) -> None:
    set_session_cookie(response, issued, clock=clock)
    response.status_code = status.HTTP_204_NO_CONTENT


@router.post("/options", operation_id="auth_step_up_options")
async def options(request: Request, db: Uow, user: Me, clock: ClockDep) -> dict[str, Any]:
    """WebAuthn request options limited to the signed-in user's passkeys."""
    await _require_passkeys(request)
    rp = RelyingParty.from_settings(_settings(request))
    return await step_up_options(db, request.app.state.redis, user=user, rp=rp, clock=clock)


@router.post(
    "",
    operation_id="auth_step_up",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={202: {"description": "Confirmation link sent to the account's address"}},
)
async def step_up(
    body: StepUpRequest,
    request: Request,
    response: Response,
    db: Uow,
    user: Me,
    clock: ClockDep,
    policy: PolicyDep,
) -> None:
    """`passkey`: 204 and a rotated session. `magic_link`: 202, a link is e-mailed."""
    ip = client_ip(request.scope, proxy_secret=_secret(request))
    if body.method == "magic_link":
        settings = _settings(request)
        email = await request_step_up_link(
            db, request.app.state.queue, user=user, ip=ip, settings=settings, clock=clock
        )
        await limit_magic_link_requests(
            request.app.state.redis,
            email=email,
            ip=ip,
            secret=settings.secret_key.get_secret_value(),
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return
    await _require_passkeys(request)
    issued = await step_up_with_passkey(
        db,
        request.app.state.redis,
        user=user,
        credential=body.credential or {},
        rp=RelyingParty.from_settings(_settings(request)),
        policy=policy,
        clock=clock,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        country=client_country(request.scope, proxy_secret=_secret(request)),
    )
    _rotated(response, issued, clock)


@router.post("/verify", operation_id="auth_step_up_verify", status_code=204)
async def verify(
    body: StepUpVerify,
    request: Request,
    response: Response,
    db: Uow,
    user: Me,
    clock: ClockDep,
    policy: PolicyDep,
) -> None:
    """Use the e-mailed confirmation link (in the browser of the session it confirms)."""
    issued = await verify_step_up_link(
        db,
        body.token,
        user=user,
        policy=policy,
        clock=clock,
        ip=client_ip(request.scope, proxy_secret=_secret(request)),
        user_agent=request.headers.get("user-agent"),
        country=client_country(request.scope, proxy_secret=_secret(request)),
    )
    _rotated(response, issued, clock)
