"""Opaque server-side sessions (ADR-0008, section 13.2, P1-T02b).

A session token is 256 random bits; only its SHA-256 is stored. A session ends at its absolute
expiry (30 days, staff 12 hours), after 14 days without activity, or when revoked. Activity is
written at most every 5 minutes so that reads do not write to the database on every request.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.modules.identity import repository
from trovelya.modules.identity.models import SessionKind
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

TOKEN_BYTES = 32
USER_AGENT_MAX = 512


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    web_ttl: timedelta
    admin_ttl: timedelta
    idle: timedelta
    touch_interval: timedelta = timedelta(minutes=5)

    @classmethod
    def from_settings(cls, settings: Settings) -> "SessionPolicy":
        return cls(
            web_ttl=timedelta(days=settings.session_ttl_days),
            admin_ttl=timedelta(hours=settings.admin_session_ttl_hours),
            idle=timedelta(days=settings.session_idle_days),
        )

    def ttl_for(self, kind: SessionKind) -> timedelta:
        return self.admin_ttl if kind == "admin" else self.web_ttl


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    session_id: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    session_id: UUID
    kind: SessionKind
    mfa_at: datetime | None
    is_staff: bool
    profile_completed: bool


@dataclass(frozen=True, slots=True)
class SessionSummary:
    id: UUID
    current: bool
    created_at: datetime
    last_used_at: datetime
    device_label: str | None
    country_code: str | None


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


_BROWSERS = (
    (re.compile(r"Edg/"), "Edge"),
    (re.compile(r"OPR/|Opera"), "Opera"),
    (re.compile(r"Firefox/"), "Firefox"),
    (re.compile(r"Chrome/|CriOS/"), "Chrome"),
    (re.compile(r"Safari/|AppleWebKit/"), "Safari"),
)
_SYSTEMS = (
    (re.compile(r"iPhone|iPad"), "iOS"),
    (re.compile(r"Android"), "Android"),
    (re.compile(r"Mac OS X|Macintosh"), "macOS"),
    (re.compile(r"Windows"), "Windows"),
    (re.compile(r"Linux"), "Linux"),
)


def device_label(user_agent: str | None) -> str | None:
    """Coarse "Browser · System" label shown in the session list; never the full user agent."""
    if not user_agent:
        return None
    browser = next((name for pattern, name in _BROWSERS if pattern.search(user_agent)), None)
    system = next((name for pattern, name in _SYSTEMS if pattern.search(user_agent)), None)
    parts = [part for part in (browser, system) if part]
    return " · ".join(parts) or None


async def create_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    kind: SessionKind,
    ip: str | None,
    user_agent: str | None,
    country: str | None,
    strong: bool,
    policy: SessionPolicy,
    clock: Clock,
) -> IssuedSession:
    """New session for a successful sign-in. `strong` (magic link, passkey) sets `mfa_at`."""
    now = clock.now()
    token = secrets.token_urlsafe(TOKEN_BYTES)
    session_id = new_id()
    expires_at = now + policy.ttl_for(kind)
    user_agent = user_agent[:USER_AGENT_MAX] if user_agent else None
    await repository.insert_session(
        db,
        session_id=session_id,
        user_id=user_id,
        token_hash=hash_token(token),
        kind=kind,
        now=now,
        expires_at=expires_at,
        ip=ip,
        user_agent=user_agent,
        device_label=device_label(user_agent),
        country=country,
        mfa_at=now if strong else None,
    )
    return IssuedSession(token=token, session_id=session_id, expires_at=expires_at)


async def resolve_session(
    db: AsyncSession, token: str, *, policy: SessionPolicy, clock: Clock
) -> CurrentUser | None:
    now = clock.now()
    row = await repository.find_active_session(
        db, hash_token(token), now=now, idle_cutoff=now - policy.idle
    )
    if row is None:
        return None
    if now - row.last_used_at >= policy.touch_interval:
        await repository.touch_session(db, row.id, now=now)
    return CurrentUser(
        id=row.user_id,
        session_id=row.id,
        kind=row.kind,
        mfa_at=row.mfa_at,
        is_staff=row.is_staff,
        profile_completed=row.profile_completed,
    )


async def rotate_session(
    db: AsyncSession,
    *,
    current: CurrentUser,
    strong: bool,
    policy: SessionPolicy,
    clock: Clock,
    ip: str | None = None,
    user_agent: str | None = None,
    country: str | None = None,
) -> IssuedSession:
    """Replace the current session by a new token (step-up, anti-fixation); the old one dies."""
    await repository.revoke_session(
        db, session_id=current.session_id, user_id=current.id, now=clock.now()
    )
    return await create_session(
        db,
        user_id=current.id,
        kind=current.kind,
        ip=ip,
        user_agent=user_agent,
        country=country,
        strong=strong,
        policy=policy,
        clock=clock,
    )


async def revoke_session(
    db: AsyncSession, *, user_id: UUID, session_id: UUID, clock: Clock
) -> bool:
    """False when the session is not this user's (or already revoked): the route answers 404."""
    return await repository.revoke_session(
        db, session_id=session_id, user_id=user_id, now=clock.now()
    )


async def revoke_other_sessions(db: AsyncSession, *, current: CurrentUser, clock: Clock) -> None:
    await repository.revoke_sessions(
        db, user_id=current.id, except_id=current.session_id, now=clock.now()
    )


async def list_sessions(
    db: AsyncSession, *, current: CurrentUser, policy: SessionPolicy, clock: Clock
) -> list[SessionSummary]:
    now = clock.now()
    rows = await repository.list_active_sessions(
        db, user_id=current.id, now=now, idle_cutoff=now - policy.idle
    )
    return [
        SessionSummary(
            id=row.id,
            current=row.id == current.session_id,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            device_label=row.device_label,
            country_code=row.country_code,
        )
        for row in rows
    ]
