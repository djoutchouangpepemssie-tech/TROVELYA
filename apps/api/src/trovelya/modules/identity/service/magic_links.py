"""Passwordless sign-in by magic link (sections 11.5 and 13.2, P1-T02c part 2).

- No account enumeration: a request does exactly the same work whether the address is known
  or not (the account is only created when the link is used), and always answers 202.
- The link carries a 256-bit token in the URL fragment, which browsers never send to servers
  or put in `Referer`; the page asks for a click (POST) so mail scanners cannot use it.
- Single use, 15 minutes [PARAM `auth.magic_link_ttl_min`], only its SHA-256 is stored.
- Limits: 5 requests per hour per address, 20 per hour per IP (11.4); Redis keys hold only
  keyed hashes of the address and IP.
"""

import secrets
import string
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.config import Settings
from trovelya.core.db import commit
from trovelya.core.email import JobQueue, enqueue_email
from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.ratelimit import client_fingerprint, hit
from trovelya.modules.identity import repository
from trovelya.modules.identity.emails import magic_link_message
from trovelya.modules.identity.models import BLOCKED_STATUSES
from trovelya.modules.identity.service.sessions import (
    IssuedSession,
    SessionPolicy,
    create_session,
    hash_token,
)
from trovelya.shared.clock import Clock
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id

logger = structlog.get_logger(__name__)

TOKEN_BYTES = 32
DEFAULT_TTL_MIN = 15
PURGE_AFTER = timedelta(hours=24)
PER_EMAIL_PER_HOUR = 5
PER_IP_PER_HOUR = 20
_USERNAME_ALPHABET = string.ascii_lowercase + string.digits
_BLOCKED = {status.value for status in BLOCKED_STATUSES}


@dataclass(frozen=True, slots=True)
class SignIn:
    user_id: UUID
    is_new: bool
    profile_completed: bool
    session: IssuedSession


async def limit_requests(redis: Redis, *, email: str, ip: str, secret: str) -> None:
    """429 beyond 20 requests per hour per IP or 5 per hour per address (fails open)."""
    checks = (
        (f"ml:ip:{client_fingerprint(ip, secret=secret)}", PER_IP_PER_HOUR),
        (f"ml:email:{client_fingerprint(email.lower(), secret=secret)}", PER_EMAIL_PER_HOUR),
    )
    for key, limit in checks:
        try:
            retry_after = await hit(redis, key, limit=limit, window_s=3600)
        except Exception as exc:  # noqa: BLE001 — fail open, see core/ratelimit.py
            logger.warning("ratelimit.redis_unavailable", error=type(exc).__name__)
            return
        if retry_after is not None:
            raise AppError(ErrorCode.RATE_LIMITED, 429, headers={"Retry-After": str(retry_after)})


async def magic_link_ttl_min(db: AsyncSession) -> int:
    """Lifetime of a sign-in link, in minutes [PARAM `auth.magic_link_ttl_min`]."""
    return await repository.setting_int(db, "auth.magic_link_ttl_min", default=DEFAULT_TTL_MIN)


async def issue_magic_link(
    db: AsyncSession,
    *,
    email: str,
    ip: str | None,
    settings: Settings,
    clock: Clock,
    ttl: timedelta | None = None,
) -> tuple[str, int]:
    """Stores a new sign-in link; answers the link and its lifetime in minutes."""
    now = clock.now()
    ttl_min = await magic_link_ttl_min(db)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    await repository.insert_magic_link(
        db,
        link_id=new_id(),
        email=email,
        token_hash=hash_token(token),
        purpose="login",
        expires_at=now + (ttl if ttl is not None else timedelta(minutes=ttl_min)),
        ip=ip if ip != "unknown" else None,
        now=now,
    )
    return f"{settings.web_origin.rstrip('/')}/fr/verifier#token={token}", ttl_min


async def request_magic_link(
    db: AsyncSession,
    queue: JobQueue,
    *,
    email: str,
    ip: str,
    settings: Settings,
    clock: Clock,
) -> None:
    link, ttl_min = await issue_magic_link(db, email=email, ip=ip, settings=settings, clock=clock)
    await enqueue_email(
        db, queue, magic_link_message(to=email, link=link, ttl_minutes=ttl_min), settings=settings
    )


def provisional_username() -> str:
    return "membre_" + "".join(secrets.choice(_USERNAME_ALPHABET) for _ in range(8))


async def verify_magic_link(
    db: AsyncSession,
    token: str,
    *,
    ip: str | None,
    user_agent: str | None,
    country: str | None,
    policy: SessionPolicy,
    clock: Clock,
) -> SignIn:
    """Consume the link, create the account on first use, open a strong web session.

    Any failure (unknown, expired or used link, staff or blocked account) gives the same
    `magic_link_invalid`, so the answer reveals nothing about the account.
    """
    now = clock.now()
    email = await repository.consume_magic_link(
        db, token_hash=hash_token(token), purpose="login", now=now
    )
    if email is None:
        raise AppError(ErrorCode.MAGIC_LINK_INVALID, 400)

    is_new = await repository.create_user(
        db,
        user_id=new_id(),
        email=email,
        username=provisional_username(),
        display_name="Membre",
        now=now,
    )
    user = await repository.find_user_by_email(db, email)
    if user is None or user.is_staff or user.status in _BLOCKED:
        # Staff accounts sign in with a passkey only (ADR-0018); blocked accounts not at all.
        # The request rolls back, which is harmless: the same link is refused every time.
        raise AppError(ErrorCode.MAGIC_LINK_INVALID, 400)
    if is_new:
        await emit_event(
            db, type="user.registered", aggregate_type="user", aggregate_id=user.id, payload={}
        )
    else:
        await repository.mark_email_verified(db, user.id, now=now)

    issued = await create_session(
        db,
        user_id=user.id,
        kind="web",
        ip=ip,
        user_agent=user_agent,
        country=country,
        strong=True,
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
        user_id=user.id,
        is_new=is_new,
        profile_completed=user.profile_completed,
        session=issued,
    )


async def purge_expired_magic_links(
    sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock
) -> int:
    """Daily job: links (address, IP) are kept 24 hours after they expire (docs/data/PII.md)."""
    async with sessionmaker() as db:
        purged = await repository.purge_magic_links(db, cutoff=clock.now() - PURGE_AFTER)
        await commit(db)
    return purged
