"""SQL of the identity module. Only this module's service reads or writes these tables."""

from datetime import datetime
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
