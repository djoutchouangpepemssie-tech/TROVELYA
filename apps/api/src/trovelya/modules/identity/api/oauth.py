"""Sign-in with Google (and Apple later): `/v1/auth/oauth/{provider}/*`.

Browser navigations, not API calls: both routes answer with a redirect. Through the web relay
the provider calls back on the web origin, so the cookies stay first-party (ADR-0015).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from trovelya.core.client_ip import client_country, client_ip
from trovelya.core.config import Settings
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.adapters.oidc import OidcProvider
from trovelya.modules.identity.service import (
    SessionPolicy,
    get_clock,
    get_session_policy,
    set_session_cookie,
)
from trovelya.modules.identity.service.auth import Uow
from trovelya.modules.identity.service.oauth import (
    OAUTH_COOKIE,
    STATE_TTL_S,
    finish_oauth,
    start_oauth,
)
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/auth/oauth", tags=["auth"])


async def _provider(provider: str, request: Request) -> OidcProvider:
    """404 for an unknown provider, one without credentials, or one whose flag is off."""
    configured: dict[str, OidcProvider] = request.app.state.oidc
    if provider not in configured or not await request.app.state.flags.is_enabled(
        f"auth.oauth_{provider}"
    ):
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return configured[provider]


ProviderDep = Annotated[OidcProvider, Depends(_provider)]


def _web(request: Request, path: str) -> str:
    settings: Settings = request.app.state.settings
    return f"{settings.web_origin.rstrip('/')}{path}"


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


@router.get("/{provider}/callback", operation_id="auth_oauth_callback", status_code=302)
async def oauth_callback(
    provider: ProviderDep,
    request: Request,
    db: Uow,
    clock: Annotated[Clock, Depends(get_clock)],
    policy: Annotated[SessionPolicy, Depends(get_session_policy)],
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Back from the provider: open a session, then go to onboarding or the home page.

    Any failure (cancelled consent, replayed or foreign state, invalid token, refused
    account) sends the browser to the sign-in page with an error code.
    """
    settings: Settings = request.app.state.settings
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
        set_session_cookie(response, sign_in.session, clock=clock)
    response.delete_cookie(OAUTH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response
