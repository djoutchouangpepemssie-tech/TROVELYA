"""Passkeys: `/v1/auth/passkeys/*` (registration, sign-in, staff enrolment) and
`/v1/me/passkeys` (management).

While the `auth.passkeys` flag is off, members can neither add nor manage passkeys (404). Signing
in with a passkey and the staff enrolment stay open: staff accounts sign in by passkey only
(ADR-0018), and a member cannot hold a passkey while the flag is off.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from trovelya.core.client_ip import client_country, client_ip
from trovelya.core.config import Settings
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.schemas import (
    PasskeyList,
    PasskeyLoginVerify,
    PasskeyOut,
    PasskeyRegisterVerify,
    PasskeyRename,
    SignInResult,
    StaffEnrolmentOptions,
    StaffEnrolmentVerify,
)
from trovelya.modules.identity.service import (
    CurrentUser,
    SessionPolicy,
    consents,
    get_clock,
    get_session_policy,
    set_session_cookie,
    staff_accounts,
)
from trovelya.modules.identity.service import passkeys as service
from trovelya.modules.identity.service.auth import Uow, completed_user, recent_mfa_user
from trovelya.shared.clock import Clock


async def _enabled(request: Request) -> None:
    if not await request.app.state.flags.is_enabled("auth.passkeys"):
        raise AppError(ErrorCode.NOT_FOUND, 404)


auth_router = APIRouter(prefix="/v1/auth/passkeys", tags=["auth"], dependencies=[Depends(_enabled)])
sign_in_router = APIRouter(prefix="/v1/auth/passkeys", tags=["auth"])
me_router = APIRouter(prefix="/v1/me/passkeys", tags=["me"], dependencies=[Depends(_enabled)])

ClockDep = Annotated[Clock, Depends(get_clock)]
Me = Annotated[CurrentUser, Depends(completed_user)]
StepUp = Annotated[CurrentUser, Depends(recent_mfa_user)]


def _rp(request: Request) -> service.RelyingParty:
    settings: Settings = request.app.state.settings
    return service.RelyingParty.from_settings(settings)


@auth_router.post("/register/options", operation_id="auth_passkeys_register_options")
async def register_options(
    request: Request, db: Uow, user: StepUp, clock: ClockDep
) -> dict[str, Any]:
    """WebAuthn creation options for `navigator.credentials.create()`."""
    return await service.registration_options(
        db, request.app.state.redis, user_id=user.id, rp=_rp(request), clock=clock
    )


@auth_router.post(
    "/register/verify",
    operation_id="auth_passkeys_register_verify",
    status_code=status.HTTP_201_CREATED,
)
async def register_verify(
    body: PasskeyRegisterVerify, request: Request, db: Uow, user: StepUp, clock: ClockDep
) -> PasskeyOut:
    row = await service.register_passkey(
        db,
        request.app.state.redis,
        user=user,
        credential=body.credential,
        name=body.name,
        rp=_rp(request),
        clock=clock,
    )
    return PasskeyOut.model_validate(row, from_attributes=True)


@sign_in_router.post("/login/options", operation_id="auth_passkeys_login_options")
async def login_options(request: Request, db: Uow, clock: ClockDep) -> dict[str, Any]:
    """WebAuthn request options for `navigator.credentials.get()` (any passkey of this site)."""
    return await service.login_options(db, request.app.state.redis, rp=_rp(request), clock=clock)


@sign_in_router.post("/login/verify", operation_id="auth_passkeys_login_verify")
async def login_verify(
    body: PasskeyLoginVerify,
    request: Request,
    response: Response,
    db: Uow,
    clock: ClockDep,
    policy: Annotated[SessionPolicy, Depends(get_session_policy)],
) -> SignInResult:
    secret = request.app.state.settings.proxy_shared_secret.get_secret_value()
    sign_in = await service.login_with_passkey(
        db,
        request.app.state.redis,
        credential=body.credential,
        ip=client_ip(request.scope, proxy_secret=secret),
        user_agent=request.headers.get("user-agent"),
        country=client_country(request.scope, proxy_secret=secret),
        rp=_rp(request),
        policy=policy,
        clock=clock,
    )
    await consents.attach_on_sign_in(
        db, cookie=request.cookies.get(consents.ANON_COOKIE), user_id=sign_in.user_id
    )
    set_session_cookie(response, sign_in.session, clock=clock)
    return SignInResult(
        user_id=sign_in.user_id, is_new=False, profile_completed=sign_in.profile_completed
    )


@me_router.get("", operation_id="me_passkeys_list")
async def get_passkeys(db: Uow, user: Me) -> PasskeyList:
    rows = await service.list_passkeys(db, user=user)
    return PasskeyList(data=[PasskeyOut.model_validate(r, from_attributes=True) for r in rows])


@me_router.patch("/{passkey_id}", operation_id="me_passkeys_rename")
async def patch_passkey(passkey_id: UUID, body: PasskeyRename, db: Uow, user: Me) -> PasskeyOut:
    row = await service.rename_passkey(db, user=user, passkey_id=passkey_id, name=body.name)
    return PasskeyOut.model_validate(row, from_attributes=True)


@me_router.delete(
    "/{passkey_id}", operation_id="me_passkeys_delete", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_passkey(passkey_id: UUID, db: Uow, user: StepUp) -> None:
    await service.delete_passkey(db, user=user, passkey_id=passkey_id)


@sign_in_router.post(
    "/enrol/options",
    operation_id="auth_passkeys_enrol_options",
    responses={400: {"description": "enrolment_invalid"}},
)
async def enrol_options(
    body: StaffEnrolmentOptions, request: Request, db: Uow, clock: ClockDep
) -> dict[str, Any]:
    """Staff enrolment (ADR-0018): creation options for the account of the link."""
    return await staff_accounts.enrolment_options(
        db, request.app.state.redis, token=body.enrolment_token, rp=_rp(request), clock=clock
    )


@sign_in_router.post(
    "/enrol/verify",
    operation_id="auth_passkeys_enrol_verify",
    responses={400: {"description": "enrolment_invalid or passkey_invalid"}},
)
async def enrol_verify(
    body: StaffEnrolmentVerify,
    request: Request,
    response: Response,
    db: Uow,
    clock: ClockDep,
    policy: Annotated[SessionPolicy, Depends(get_session_policy)],
) -> SignInResult:
    """Registers the staff account's first passkey (single-use link) and opens an admin
    session (cookie `__Host-trv_session`)."""
    secret = request.app.state.settings.proxy_shared_secret.get_secret_value()
    sign_in = await staff_accounts.enrol(
        db,
        request.app.state.redis,
        token=body.enrolment_token,
        credential=body.credential,
        name=body.name,
        ip=client_ip(request.scope, proxy_secret=secret),
        user_agent=request.headers.get("user-agent"),
        country=client_country(request.scope, proxy_secret=secret),
        rp=_rp(request),
        policy=policy,
        clock=clock,
    )
    set_session_cookie(response, sign_in.session, clock=clock)
    return SignInResult(user_id=sign_in.user_id, is_new=False, profile_completed=True)
