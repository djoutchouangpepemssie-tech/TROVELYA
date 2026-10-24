"""Step-up (section 13.2): renew the proof of a strong sign-in before a sensitive action.

Two ways: an assertion of one of the user's passkeys, or a single-use link e-mailed to the
account's address (purpose `step_up`, opened in the same browser). Both rotate the session:
a new token carrying `mfa_at`, the old one revoked.
"""

import secrets
from datetime import timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.email import JobQueue, enqueue_email
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.modules.identity.emails import step_up_message
from trovelya.modules.identity.service.magic_links import DEFAULT_TTL_MIN, TOKEN_BYTES
from trovelya.modules.identity.service.passkeys import RelyingParty, verify_step_up_assertion
from trovelya.modules.identity.service.sessions import (
    CurrentUser,
    IssuedSession,
    SessionPolicy,
    hash_token,
    rotate_session,
)
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

PURPOSE = "step_up"


async def step_up_with_passkey(
    db: AsyncSession,
    redis: Redis,
    *,
    user: CurrentUser,
    credential: dict[str, Any],
    rp: RelyingParty,
    policy: SessionPolicy,
    clock: Clock,
    ip: str | None,
    user_agent: str | None,
    country: str | None,
) -> IssuedSession:
    await verify_step_up_assertion(db, redis, user=user, credential=credential, rp=rp, clock=clock)
    return await rotate_session(
        db,
        current=user,
        strong=True,
        policy=policy,
        clock=clock,
        ip=ip,
        user_agent=user_agent,
        country=country,
    )


async def request_step_up_link(
    db: AsyncSession,
    queue: JobQueue,
    *,
    user: CurrentUser,
    ip: str,
    settings: Settings,
    clock: Clock,
) -> str:
    """E-mail a confirmation link to the account's address; returns that address."""
    now = clock.now()
    email = await repository.user_email(db, user.id)
    ttl_min = await repository.setting_int(db, "auth.magic_link_ttl_min", default=DEFAULT_TTL_MIN)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    await repository.insert_magic_link(
        db,
        link_id=new_id(),
        email=email,
        token_hash=hash_token(token),
        purpose=PURPOSE,
        expires_at=now + timedelta(minutes=ttl_min),
        ip=ip if ip != "unknown" else None,
        now=now,
    )
    link = f"{settings.web_origin.rstrip('/')}/fr/confirmer#token={token}"
    message = step_up_message(to=email, link=link, ttl_minutes=ttl_min)
    await enqueue_email(db, queue, message, settings=settings)
    return email


async def verify_step_up_link(
    db: AsyncSession,
    token: str,
    *,
    user: CurrentUser,
    policy: SessionPolicy,
    clock: Clock,
    ip: str | None,
    user_agent: str | None,
    country: str | None,
) -> IssuedSession:
    """The link must be a step-up link sent to this account. A refusal rolls the request back,
    so another account cannot burn the owner's link; it stays single use for the owner."""
    email = await repository.consume_magic_link(
        db, token_hash=hash_token(token), purpose=PURPOSE, now=clock.now()
    )
    if email is None or email != await repository.user_email(db, user.id):
        raise AppError(ErrorCode.MAGIC_LINK_INVALID, 400)
    return await rotate_session(
        db,
        current=user,
        strong=True,
        policy=policy,
        clock=clock,
        ip=ip,
        user_agent=user_agent,
        country=country,
    )
