"""Sign-in with Google and Apple: `/v1/auth/oauth/{provider}/*`.

Browser navigations, not API calls: every route answers with a redirect. Through the web relay
the provider calls back on the web origin, so the cookies stay first-party (ADR-0015).
"""

from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from trovelya.core.client_ip import client_country, client_ip
from trovelya.core.config import Settings
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.adapters.oidc import OidcProvider
from trovelya.modules.identity.service import (
    SessionPolicy,
    consents,
    get_clock,
    get_session_policy,
    set_session_cookie,
)
from trovelya.modules.identity.service.auth import Uow
from trovelya.modules.identity.service.oauth import (
    OAUTH_COOKIE,
    STATE_TTL_S,
    finish_oauth,
    park_form_post,
    start_oauth,
    take_form_post,
)
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/auth/oauth", tags=["auth"])
FORM_POST = "form_post"
MAX_FORM_BYTES = 16_384


async def _provider(provider: str, request: Request) -> OidcProvider:
    """404 for an unknown provider, one without credentials, or one whose flag is off."""
    configured: dict[str, OidcProvider] = request.app.state.oidc
    if provider not in configured or not await request.app.state.flags.is_enabled(
        f"auth.oauth_{provider}"
    ):
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return configured[provider]


ProviderDep = Annotated[OidcProvider, Depends(_provider)]
ClockDep = Annotated[Clock, Depends(get_clock)]
PolicyDep = Annotated[SessionPolicy, Depends(get_session_policy)]


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _web(request: Request, path: str) -> str:
    return f"{_settings(request).web_origin.rstrip('/')}{path}"


def _require_mode(provider: OidcProvider, *, form_post: bool) -> None:
    if (provider.config.response_mode == FORM_POST) != form_post:
        raise AppError(ErrorCode.NOT_FOUND, 404)


@router.get("/{provider}/start", operation_id="auth_oauth_start", status_code=302)
async def oauth_start(provider: ProviderDep, request: Request) -> RedirectResponse:
    """Redirect to the provider's consent page."""
    started = await start_oauth(request.app.state.redis, provider)
    response = RedirectResponse(started.redirect_url, status_code=302)
    response.set_cookie(
        OAUTH_COOKIE,
        started.cookie_value,
        max_age=STATE_TTL_S,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


async def _complete(
    request: Request,
    provider: OidcProvider,
    db: Uow,
    clock: Clock,
    policy: SessionPolicy,
    *,
    code: str | None,
    state: str | None,
) -> RedirectResponse:
    """Open a session, then go to onboarding or the home page.

    Any failure (cancelled consent, replayed or foreign state, invalid token, refused
    account) sends the browser to the sign-in page with an error code.
    """
    settings = _settings(request)
    secret = settings.proxy_shared_secret.get_secret_value()
    try:
        if code is None or state is None:
            raise AppError(ErrorCode.OAUTH_FAILED, 400)
        sign_in = await finish_oauth(
            db,
            request.app.state.redis,
            request.app.state.queue,
            provider,
            code=code,
            state=state,
            cookie=request.cookies.get(OAUTH_COOKIE),
            ip=client_ip(request.scope, proxy_secret=secret),
            user_agent=request.headers.get("user-agent"),
            country=client_country(request.scope, proxy_secret=secret),
            policy=policy,
            settings=settings,
            clock=clock,
        )
    except AppError as exc:
        response = RedirectResponse(_web(request, f"/fr/connexion?erreur={exc.code}"), 302)
    else:
        target = "/fr" if sign_in.profile_completed else "/fr/bienvenue"
        response = RedirectResponse(_web(request, target), status_code=302)
        await consents.attach_on_sign_in(
            db, cookie=request.cookies.get(consents.ANON_COOKIE), user_id=sign_in.user_id
        )
        set_session_cookie(response, sign_in.session, clock=clock)
    response.delete_cookie(OAUTH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.get("/{provider}/callback", operation_id="auth_oauth_callback", status_code=302)
async def oauth_callback(
    provider: ProviderDep,
    request: Request,
    db: Uow,
    clock: ClockDep,
    policy: PolicyDep,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Back from the provider (Google): query string `code` and `state`."""
    _require_mode(provider, form_post=False)
    return await _complete(request, provider, db, clock, policy, code=code, state=state)


@router.post("/{provider}/callback", operation_id="auth_oauth_callback_form", status_code=303)
async def oauth_callback_form(provider: ProviderDep, request: Request) -> RedirectResponse:
    """Back from Apple by a cross-site POST: park the answer, continue with a same-site GET."""
    _require_mode(provider, form_post=True)
    body = await request.body()
    if len(body) > MAX_FORM_BYTES:
        raise AppError(ErrorCode.BAD_REQUEST, 400)
    form = {k: v[0] for k, v in parse_qs(body.decode(errors="replace")).items()}
    code, state = form.get("code"), form.get("state")
    if code is None or state is None:
        return RedirectResponse(_web(request, "/fr/connexion?erreur=oauth_failed"), 303)
    ref = await park_form_post(request.app.state.redis, code=code, state=state)
    name = provider.config.name
    return RedirectResponse(_web(request, f"/api/v1/auth/oauth/{name}/finish?ref={ref}"), 303)


@router.get("/{provider}/finish", operation_id="auth_oauth_finish", status_code=302)
async def oauth_finish(
    provider: ProviderDep,
    request: Request,
    db: Uow,
    clock: ClockDep,
    policy: PolicyDep,
    ref: str = "",
) -> RedirectResponse:
    """Second half of the form_post return: the `Lax` cookie is sent on this same-site GET."""
    _require_mode(provider, form_post=True)
    try:
        code, state = await take_form_post(request.app.state.redis, ref)
    except AppError:
        code = state = None
    return await _complete(request, provider, db, clock, policy, code=code, state=state)
