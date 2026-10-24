"""SQL of the identity module. Only this module's service reads or writes these tables."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.identity.models import BLOCKED_STATUSES, SessionKind

_BLOCKED = [status.value for status in BLOCKED_STATUSES]

_INSERT_SESSION = text(
    "INSERT INTO sessions (id, user_id, token_hash, kind, created_at, last_used_at, expires_at,"
    " ip, user_agent, device_label, country_code, mfa_at)"
    " VALUES (:id, :user_id, :token_hash, :kind, :now, :now, :expires_at, CAST(:ip AS inet),"
    " :user_agent, :device_label, :country, :mfa_at)"
)

_FIND_ACTIVE = text(
    "SELECT s.id, s.user_id, s.kind, s.mfa_at, s.last_used_at, s.expires_at,"
    " u.is_staff, u.profile_completed_at IS NOT NULL AS profile_completed"
    " FROM sessions s JOIN users u ON u.id = s.user_id"
    " WHERE s.token_hash = :token_hash AND s.revoked_at IS NULL"
    " AND s.expires_at > :now AND s.last_used_at > :idle_cutoff"
    " AND u.status::text <> ALL(:blocked)"
)

_TOUCH = text("UPDATE sessions SET last_used_at = :now WHERE id = :id")

_REVOKE_ONE = text(
    "UPDATE sessions SET revoked_at = :now"
    " WHERE id = :id AND user_id = :user_id AND revoked_at IS NULL RETURNING id"
)

_REVOKE_ALL = text(
    "UPDATE sessions SET revoked_at = :now"
    " WHERE user_id = :user_id AND revoked_at IS NULL"
    " AND (CAST(:except_id AS uuid) IS NULL OR id <> :except_id)"
)

_LIST_ACTIVE = text(
    "SELECT id, created_at, last_used_at, device_label, country_code FROM sessions"
    " WHERE user_id = :user_id AND revoked_at IS NULL"
    " AND expires_at > :now AND last_used_at > :idle_cutoff"
    " ORDER BY last_used_at DESC"
)


async def insert_session(
    db: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
    token_hash: bytes,
    kind: SessionKind,
    now: datetime,
    expires_at: datetime,
    ip: str | None,
    user_agent: str | None,
    device_label: str | None,
    country: str | None,
    mfa_at: datetime | None,
) -> None:
    await db.execute(
        _INSERT_SESSION,
        {
            "id": session_id,
            "user_id": user_id,
            "token_hash": token_hash,
            "kind": kind,
            "now": now,
            "expires_at": expires_at,
            "ip": ip,
            "user_agent": user_agent,
            "device_label": device_label,
            "country": country,
            "mfa_at": mfa_at,
        },
    )


async def find_active_session(
    db: AsyncSession, token_hash: bytes, *, now: datetime, idle_cutoff: datetime
) -> Row[Any] | None:
    result = await db.execute(
        _FIND_ACTIVE,
        {"token_hash": token_hash, "now": now, "idle_cutoff": idle_cutoff, "blocked": _BLOCKED},
    )
    return result.one_or_none()


async def touch_session(db: AsyncSession, session_id: UUID, *, now: datetime) -> None:
    await db.execute(_TOUCH, {"id": session_id, "now": now})


async def revoke_session(
    db: AsyncSession, *, session_id: UUID, user_id: UUID, now: datetime
) -> bool:
    result = await db.execute(_REVOKE_ONE, {"id": session_id, "user_id": user_id, "now": now})
    return result.one_or_none() is not None


async def revoke_sessions(
    db: AsyncSession, *, user_id: UUID, except_id: UUID | None, now: datetime
) -> None:
    await db.execute(_REVOKE_ALL, {"user_id": user_id, "except_id": except_id, "now": now})


async def list_active_sessions(
    db: AsyncSession, *, user_id: UUID, now: datetime, idle_cutoff: datetime
) -> list[Row[Any]]:
    result = await db.execute(
        _LIST_ACTIVE, {"user_id": user_id, "now": now, "idle_cutoff": idle_cutoff}
    )
    return list(result.all())


# --- Magic links and sign-up -----------------------------------------------------------------

_SETTING_INT = text("SELECT value FROM platform_settings WHERE key = :key")

_INSERT_MAGIC_LINK = text(
    "INSERT INTO magic_links (id, email, token_hash, purpose, expires_at, ip, created_at)"
    " VALUES (:id, :email, :token_hash, :purpose, :expires_at, CAST(:ip AS inet), :now)"
)

# Atomic: two concurrent clicks on the same link, only one gets the row back.
_CONSUME_MAGIC_LINK = text(
    "UPDATE magic_links SET consumed_at = :now"
    " WHERE token_hash = :token_hash AND purpose = :purpose"
    " AND consumed_at IS NULL AND expires_at > :now RETURNING email"
)

_PURGE_MAGIC_LINKS = text("DELETE FROM magic_links WHERE expires_at < :cutoff")

_FIND_USER_BY_EMAIL = text(
    "SELECT id, is_staff, status::text AS status,"
    " profile_completed_at IS NOT NULL AS profile_completed"
    " FROM users WHERE email = :email"
)

_CREATE_USER = text(
    "INSERT INTO users (id, email, username, display_name, email_verified_at, created_at)"
    " VALUES (:id, :email, :username, :display_name, :now, :now)"
    " ON CONFLICT (email) DO NOTHING RETURNING id"
)

_CREATE_PREFERENCES = text(
    "INSERT INTO user_preferences (user_id) VALUES (:user_id) ON CONFLICT DO NOTHING"
)

_MARK_EMAIL_VERIFIED = text(
    "UPDATE users SET email_verified_at = coalesce(email_verified_at, :now) WHERE id = :id"
)


async def setting_int(db: AsyncSession, key: str, *, default: int) -> int:
    value = await db.scalar(_SETTING_INT, {"key": key})
    return int(value) if value is not None else default


async def insert_magic_link(
    db: AsyncSession,
    *,
    link_id: UUID,
    email: str,
    token_hash: bytes,
    purpose: str,
    expires_at: datetime,
    ip: str | None,
    now: datetime,
) -> None:
    await db.execute(
        _INSERT_MAGIC_LINK,
        {
            "id": link_id,
            "email": email,
            "token_hash": token_hash,
            "purpose": purpose,
            "expires_at": expires_at,
            "ip": ip,
            "now": now,
        },
    )


async def consume_magic_link(
    db: AsyncSession, *, token_hash: bytes, purpose: str, now: datetime
) -> str | None:
    result = await db.execute(
        _CONSUME_MAGIC_LINK, {"token_hash": token_hash, "purpose": purpose, "now": now}
    )
    return result.scalar_one_or_none()


async def purge_magic_links(db: AsyncSession, *, cutoff: datetime) -> int:
    result = await db.execute(_PURGE_MAGIC_LINKS, {"cutoff": cutoff})
    return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]


async def find_user_by_email(db: AsyncSession, email: str) -> Row[Any] | None:
    return (await db.execute(_FIND_USER_BY_EMAIL, {"email": email})).one_or_none()


async def create_user(
    db: AsyncSession, *, user_id: UUID, email: str, username: str, display_name: str, now: datetime
) -> bool:
    """False when another request created the account for this e-mail at the same time."""
    result = await db.execute(
        _CREATE_USER,
        {
            "id": user_id,
            "email": email,
            "username": username,
            "display_name": display_name,
            "now": now,
        },
    )
    if result.scalar_one_or_none() is None:
        return False
    await db.execute(_CREATE_PREFERENCES, {"user_id": user_id})
    return True


async def mark_email_verified(db: AsyncSession, user_id: UUID, *, now: datetime) -> None:
    await db.execute(_MARK_EMAIL_VERIFIED, {"id": user_id, "now": now})


_NEW_SESSION = text(
    "SELECT s.created_at, s.device_label, s.country_code, u.email,"
    " EXISTS (SELECT 1 FROM sessions p WHERE p.user_id = s.user_id AND p.id <> s.id"
    "   AND p.created_at <= s.created_at) AS has_previous,"
    " EXISTS (SELECT 1 FROM sessions p WHERE p.user_id = s.user_id AND p.id <> s.id"
    "   AND p.created_at <= s.created_at"
    "   AND p.created_at > s.created_at - CAST(:window AS interval)"
    "   AND p.device_label IS NOT DISTINCT FROM s.device_label"
    "   AND p.country_code IS NOT DISTINCT FROM s.country_code) AS known_context"
    " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = :id"
)


async def find_session_context(
    db: AsyncSession, session_id: UUID, *, window: timedelta
) -> Row[Any] | None:
    """A session with its owner's address and whether its device and country were seen."""
    result = await db.execute(_NEW_SESSION, {"id": session_id, "window": window})
    return result.one_or_none()
