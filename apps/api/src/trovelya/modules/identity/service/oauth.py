"""Sign-in with an external account (Google; Apple later), sections 13.2 and P1-T03.

- `start`: random `state`, `nonce` and PKCE verifier kept 10 minutes in Redis under the
  SHA-256 of `state`; that hash also goes in the `__Host-trv_oauth` cookie, so the callback
  only works in the browser that started the attempt (login CSRF). Read once (`GETDEL`).
- `finish`: known identity → sign-in; unknown → the provider must assert a verified e-mail.
  A new address creates the account; an existing one with a verified address gets the
  identity attached and an information e-mail; an existing unverified address is refused.
- Staff and blocked accounts are refused like any failure. Sessions are not "strong".
- Apple answers with a cross-site POST (`form_post`), which does not carry the `SameSite=Lax`
  cookie: the code and state are parked 5 minutes under a one-time reference and the browser
  is sent to a same-site GET (`finish`), where the cookie is checked as usual.
"""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.email import JobQueue, enqueue_email
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.modules.identity.adapters.oidc import IdTokenClaims, OidcError, OidcProvider, new_pkce
from trovelya.modules.identity.emails import identity_linked_message
from trovelya.modules.identity.models import BLOCKED_STATUSES
from trovelya.modules.identity.service.alerts import security_link
from trovelya.modules.identity.service.magic_links import SignIn, provisional_username
from trovelya.modules.identity.service.sessions import SessionPolicy, create_session
from trovelya.shared.clock import Clock
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id

OAUTH_COOKIE = "__Host-trv_oauth"
STATE_TTL_S = 600
FORM_POST_TTL_S = 300
_KEY_PREFIX = "oauth:"
_PARKED_PREFIX = "oauth:post:"
_BLOCKED = {status.value for status in BLOCKED_STATUSES}
PROVIDER_LABELS = {"google": "Google", "apple": "Apple"}


@dataclass(frozen=True, slots=True)
class OAuthStart:
    redirect_url: str
    cookie_value: str


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def start_oauth(redis: Redis, provider: OidcProvider) -> OAuthStart:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = new_pkce()
    state_hash = _digest(state)
    attempt = {"provider": provider.config.name, "nonce": nonce, "verifier": verifier}
    await redis.set(_KEY_PREFIX + state_hash, json.dumps(attempt), ex=STATE_TTL_S)
    url = provider.authorization_url(state=state, nonce=nonce, code_challenge=challenge)
    return OAuthStart(redirect_url=url, cookie_value=state_hash)


async def park_form_post(redis: Redis, *, code: str, state: str) -> str:
    ref = secrets.token_urlsafe(32)
    await redis.set(
        _PARKED_PREFIX + _digest(ref),
        json.dumps({"code": code, "state": state}),
        ex=FORM_POST_TTL_S,
    )
    return ref


async def take_form_post(redis: Redis, ref: str) -> tuple[str, str]:
    raw = await redis.getdel(_PARKED_PREFIX + _digest(ref))
    if raw is None:
        raise AppError(ErrorCode.OAUTH_FAILED, 400)
    parked: dict[str, str] = json.loads(raw)
    return parked["code"], parked["state"]


async def _take_attempt(
    redis: Redis, provider: OidcProvider, *, state: str, cookie: str | None
) -> dict[str, Any]:
    state_hash = _digest(state)
    if cookie is None or not hmac.compare_digest(cookie, state_hash):
        raise AppError(ErrorCode.OAUTH_FAILED, 400)
    raw = await redis.getdel(_KEY_PREFIX + state_hash)
    if raw is None:
        raise AppError(ErrorCode.OAUTH_FAILED, 400)
    attempt: dict[str, Any] = json.loads(raw)
    if attempt["provider"] != provider.config.name:
        raise AppError(ErrorCode.OAUTH_FAILED, 400)
    return attempt


async def _account_for(
    db: AsyncSession,
    queue: JobQueue,
    provider: str,
    claims: IdTokenClaims,
    *,
    settings: Settings,
    clock: Clock,
) -> tuple[Row[Any], bool]:
    """(user, is_new) for these claims, creating or linking as the rules above say."""
    user = await repository.find_user_by_identity(db, provider, claims.sub)
    if user is not None:
        return user, False
    if claims.email is None or not claims.email_verified:
        raise AppError(ErrorCode.OAUTH_EMAIL_UNVERIFIED, 400)
    now = clock.now()
    is_new = await repository.create_user(
        db,
        user_id=new_id(),
        email=claims.email,
        username=provisional_username(),
        display_name="Membre",
        now=now,
    )
    user = await repository.find_user_by_email(db, claims.email)
    if user is None:
        raise AppError(ErrorCode.OAUTH_FAILED, 400)
    if not user.email_verified:
        raise AppError(ErrorCode.OAUTH_EMAIL_UNVERIFIED, 400)
    if user.is_staff or user.status in _BLOCKED:
        raise AppError(ErrorCode.OAUTH_FAILED, 400)
    await repository.link_identity(
        db, identity_id=new_id(), user_id=user.id, provider=provider, subject=claims.sub, now=now
    )
    if not is_new:
        message = identity_linked_message(
            to=claims.email,
            provider=PROVIDER_LABELS[provider],
            security_link=security_link(settings),
        )
        await enqueue_email(db, queue, message, settings=settings)
    return user, is_new


async def finish_oauth(
    db: AsyncSession,
    redis: Redis,
    queue: JobQueue,
    provider: OidcProvider,
    *,
    code: str,
    state: str,
    cookie: str | None,
    ip: str | None,
    user_agent: str | None,
    country: str | None,
    policy: SessionPolicy,
    settings: Settings,
    clock: Clock,
) -> SignIn:
    attempt = await _take_attempt(redis, provider, state=state, cookie=cookie)
    try:
        claims = await provider.exchange(
            code, code_verifier=attempt["verifier"], nonce=attempt["nonce"], now=clock.now()
        )
    except OidcError as exc:
        raise AppError(ErrorCode.OAUTH_FAILED, 400) from exc

    name = provider.config.name
    user, is_new = await _account_for(db, queue, name, claims, settings=settings, clock=clock)
    if user.is_staff or user.status in _BLOCKED:
        # Staff accounts sign in with a passkey only (ADR-0018); blocked accounts not at all.
        raise AppError(ErrorCode.OAUTH_FAILED, 400)
    if is_new:
        await emit_event(
            db, type="user.registered", aggregate_type="user", aggregate_id=user.id, payload={}
        )
    issued = await create_session(
        db,
        user_id=user.id,
        kind="web",
        ip=ip,
        user_agent=user_agent,
        country=country,
        strong=False,
        policy=policy,
        clock=clock,
    )
    await emit_event(
        db,
        type="session.created",
        aggregate_type="user",
        aggregate_id=user.id,
        payload={"session_id": str(issued.session_id)},
    )
    return SignIn(
        user_id=user.id, is_new=is_new, profile_completed=user.profile_completed, session=issued
    )
