"""Append-only audit log (section 7.2). The hash chain is computed by the database (ADR-0014)."""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

ActorType = Literal["user", "staff", "system", "api_client"]

_INSERT = text(
    "INSERT INTO audit_log (actor_type, actor_id, approver_id, action, target_type, target_id,"
    " reason, before, after, ip, user_agent, request_id)"
    " VALUES (:actor_type, :actor_id, :approver_id, :action, :target_type, :target_id,"
    " :reason, :before, :after, CAST(:ip AS inet), :user_agent, :request_id) RETURNING id"
).bindparams(bindparam("before", type_=JSONB), bindparam("after", type_=JSONB))


async def record_audit(
    session: AsyncSession,
    *,
    actor_type: ActorType,
    actor_id: UUID | None,
    action: str,
    target_type: str,
    target_id: str,
    reason: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    approver_id: UUID | None = None,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> int:
    result = await session.execute(
        _INSERT,
        {
            "actor_type": actor_type,
            "actor_id": actor_id,
            "approver_id": approver_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "reason": reason,
            "before": before,
            "after": after,
            "ip": ip,
            "user_agent": user_agent,
            "request_id": request_id,
        },
    )
    return int(result.scalar_one())
