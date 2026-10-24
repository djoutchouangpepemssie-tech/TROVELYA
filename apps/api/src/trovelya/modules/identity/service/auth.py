"""FastAPI dependencies and cookie helpers for authenticated routes (P1-T02b).

`current_user` answers 401 `unauthenticated` without a valid session, and applies the
per-user rate limit (600 requests per minute, section 11.4; fails open like the anonymous one).
"""

from datetime import timedelta
from typing import Annotated

import structlog
from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.csrf import SESSION_COOKIE
from trovelya.core.db import get_uow
from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.ratelimit import hit
from trovelya.modules.identity import repository
from trovelya.modules.identity.service.sessions import (
    CurrentUser,
    IssuedSession,
    SessionPolicy,
    resolve_session,
)
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

Uow = Annotated[AsyncSession, Depends(get_uow)]


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_session_policy(request: Request) -> SessionPolicy:
    return SessionPolicy.from_settings(request.app.state.settings)


async def _user_rate_limit(request: Request, user_id: object) -> None:
    limit: int = request.app.state.settings.rate_limit_user_per_minute
    try:
        retry_after = await hit(
            request.app.state.redis, f"user:{user_id}", limit=limit, window_s=60
        )
    except Exception as exc:  # noqa: BLE001 — fail open, see core/ratelimit.py
        logger.warning("ratelimit.redis_unavailable", error=type(exc).__name__)
        return
    if retry_after is not None:
        raise AppError(ErrorCode.RATE_LIMITED, 429, headers={"Retry-After": str(retry_after)})


async def optional_user(request: Request, db: Uow) -> CurrentUser | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    current = await resolve_session(
        db, token, policy=get_session_policy(request), clock=get_clock(request)
    )
    if current is not None:
        await _user_rate_limit(request, current.id)
    return current


async def current_user(
    user: Annotated[CurrentUser | None, Depends(optional_user)],
) -> CurrentUser:
    if user is None:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401)
    return user


DEFAULT_STEP_UP_MAX_AGE_H = 12


async def completed_user(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """Every signed-in route except the account itself, profile completion, sessions,
    consents, erasure and sign-out: `403 profile_incomplete` until the profile is completed."""
    if not user.profile_completed:
        raise AppError(ErrorCode.PROFILE_INCOMPLETE, 403)
    return user


async def recent_mfa_user(
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(completed_user)],
) -> CurrentUser:
    """For sensitive actions (13.2): a strong sign-in less than `auth.step_up_max_age_h` old.

    Otherwise `403 step_up_required`, and the client asks for a passkey or an e-mailed link.
    """
    max_age_h = await repository.setting_int(
        db, "auth.step_up_max_age_h", default=DEFAULT_STEP_UP_MAX_AGE_H
    )
    now = get_clock(request).now()
    if user.mfa_at is None or user.mfa_at <= now - timedelta(hours=max_age_h):
        raise AppError(ErrorCode.STEP_UP_REQUIRED, 403)
    return user


def set_session_cookie(response: Response, issued: IssuedSession, *, clock: Clock) -> None:
    max_age = int((issued.expires_at - clock.now()).total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
