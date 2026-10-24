"""Sign-in and sign-out routes (`/v1/auth/*`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from trovelya.core.client_ip import client_country, client_ip
from trovelya.core.config import Settings
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.schemas import (
    EmailChangeVerify,
    MagicLinkRequest,
    MagicLinkVerify,
    SignInResult,
)
from trovelya.modules.identity.service import (
    CurrentUser,
    SessionPolicy,
    clear_session_cookie,
    current_user,
    get_clock,
    get_session_policy,
    limit_magic_link_requests,
    request_magic_link,
    revoke_session,
    set_session_cookie,
    verify_magic_link,
)
from trovelya.modules.identity.service.auth import Uow
from trovelya.modules.identity.service.email_change import verify_email_change
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/auth", tags=["auth"])

ClockDep = Annotated[Clock, Depends(get_clock)]


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.post(
    "/magic-link", operation_id="auth_magic_link_request", status_code=status.HTTP_202_ACCEPTED
)
async def post_magic_link(
    body: MagicLinkRequest, request: Request, db: Uow, clock: ClockDep
) -> dict[str, str]:
    """Send a sign-in link. Same answer whether the address has an account or not."""
    settings = _settings(request)
    ip = client_ip(request.scope, proxy_secret=settings.proxy_shared_secret.get_secret_value())
    if not await request.app.state.captcha.verify(body.captcha_token, ip=ip):
        raise AppError(ErrorCode.CAPTCHA_FAILED, 400)
    await limit_magic_link_requests(
        request.app.state.redis,
        email=body.email,
        ip=ip,
        secret=settings.secret_key.get_secret_value(),
    )
    await request_magic_link(
        db, request.app.state.queue, email=body.email, ip=ip, settings=settings, clock=clock
    )
    return {}


@router.post("/magic-link/verify", operation_id="auth_magic_link_verify")
async def post_magic_link_verify(
    body: MagicLinkVerify,
    request: Request,
    response: Response,
    db: Uow,
    clock: ClockDep,
    policy: Annotated[SessionPolicy, Depends(get_session_policy)],
) -> SignInResult:
    """Exchange the link's token for a session (cookie `__Host-trv_session`)."""
    secret = _settings(request).proxy_shared_secret.get_secret_value()
    sign_in = await verify_magic_link(
        db,
        body.token,
        ip=client_ip(request.scope, proxy_secret=secret),
        user_agent=request.headers.get("user-agent"),
        country=client_country(request.scope, proxy_secret=secret),
        policy=policy,
        clock=clock,
    )
    set_session_cookie(response, sign_in.session, clock=clock)
    return SignInResult(
        user_id=sign_in.user_id,
        is_new=sign_in.is_new,
        profile_completed=sign_in.profile_completed,
    )


@router.post("/logout", operation_id="auth_logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: Uow,
    user: Annotated[CurrentUser, Depends(current_user)],
    clock: ClockDep,
) -> None:
    """Revoke the current session and clear its cookie."""
    await revoke_session(db, user_id=user.id, session_id=user.session_id, clock=clock)
    clear_session_cookie(response)


@router.post(
    "/email-change/verify",
    operation_id="auth_email_change_verify",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def post_email_change_verify(
    body: EmailChangeVerify, request: Request, db: Uow, clock: ClockDep
) -> None:
    """Use the link sent to the new address (no session needed). The old address is told."""
    await verify_email_change(
        db, request.app.state.queue, body.token, settings=_settings(request), clock=clock
    )
