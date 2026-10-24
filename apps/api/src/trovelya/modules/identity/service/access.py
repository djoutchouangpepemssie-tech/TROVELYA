"""Named permissions, staff sessions and generic dual approval (sections 3.1 and 3.2, Q17).

A permission comes from the person's roles (`user_roles` joined with `role_permissions`). When
every role granting it requires dual approval (🔒), the action becomes an `approval_requests`
row: another person holding the same permission approves it within 24 hours, then its
registered handler runs exactly once (the row is locked). Requester and approver are both
written to the audit log.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.modules.identity.service.auth import (
    DEFAULT_STEP_UP_MAX_AGE_H,
    Uow,
    current_user,
    get_clock,
)
from trovelya.modules.identity.service.sessions import CurrentUser
from trovelya.shared.audit import record_audit
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

APPROVAL_TTL = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class Grant:
    requires_approval: bool
    limit_minor: int | None  # above it the action needs dual approval; None: no limit


async def effective_grant(db: AsyncSession, user_id: UUID, permission: str) -> Grant | None:
    """The most favourable of the person's roles; None when no role grants the permission."""
    grants = await repository.permission_grants(db, user_id, permission)
    if not grants:
        return None
    direct = [g for g in grants if not g.requires_approval]
    if not direct:
        return Grant(requires_approval=True, limit_minor=None)
    limits = [g.limit_minor for g in direct]
    return Grant(
        requires_approval=False,
        limit_minor=None if None in limits else max(int(limit) for limit in limits),
    )


async def staff_user(
    request: Request, db: Uow, user: Annotated[CurrentUser, Depends(current_user)]
) -> CurrentUser:
    """Staff routes: a staff account in an admin session (passkey sign-in, 12 h) with a recent
    strong proof; anyone else is refused with `403 forbidden`."""
    if not user.is_staff or user.kind != "admin":
        raise AppError(ErrorCode.FORBIDDEN, 403)
    max_age_h = await repository.setting_int(
        db, "auth.step_up_max_age_h", default=DEFAULT_STEP_UP_MAX_AGE_H
    )
    if user.mfa_at is None or user.mfa_at <= get_clock(request).now() - timedelta(hours=max_age_h):
        raise AppError(ErrorCode.STEP_UP_REQUIRED, 403)
    return user


StaffUser = Annotated[CurrentUser, Depends(staff_user)]


@dataclass(frozen=True, slots=True)
class Authorised:
    user: CurrentUser
    grant: Grant


def require_permission(permission: str) -> Callable[..., Awaitable[Authorised]]:
    """Dependency: a staff session holding `permission` through one of its roles."""

    async def dependency(db: Uow, user: StaffUser) -> Authorised:
        grant = await effective_grant(db, user.id, permission)
        if grant is None:
            raise AppError(ErrorCode.FORBIDDEN, 403)
        return Authorised(user=user, grant=grant)

    return dependency


# --- Dual approval -----------------------------------------------------------------------------

ApprovalHandler = Callable[[AsyncSession, dict[str, Any], UUID, UUID | None], Awaitable[None]]
"""(session, payload, actor_id, approver_id): performs the action; approver None when direct."""

_HANDLERS: dict[str, ApprovalHandler] = {}


def register_approval_handler(permission: str, handler: ApprovalHandler) -> None:
    if _HANDLERS.get(permission, handler) is not handler:
        raise ValueError(f"approval handler for {permission!r} already registered")
    _HANDLERS[permission] = handler


def approval_handlers() -> Mapping[str, ApprovalHandler]:
    return MappingProxyType(_HANDLERS)


@dataclass(frozen=True, slots=True)
class ApprovalOutcome:
    approval_id: UUID | None
    status: Literal["pending", "done", "approved", "rejected"]


async def request_approval(
    db: AsyncSession,
    *,
    permission_key: str,
    requested_by: UUID,
    payload: dict[str, Any],
    reason: str,
    clock: Clock,
) -> UUID:
    now = clock.now()
    approval_id = new_id()
    await repository.insert_approval(
        db,
        approval_id=approval_id,
        permission=permission_key,
        requested_by=requested_by,
        payload=payload,
        reason=reason,
        expires_at=now + APPROVAL_TTL,
        now=now,
    )
    await record_audit(
        db,
        actor_type="staff",
        actor_id=requested_by,
        action="approval.request",
        target_type="approval_request",
        target_id=str(approval_id),
        reason=reason,
        after={"permission": permission_key, "payload": payload},
    )
    return approval_id


async def perform(
    db: AsyncSession,
    *,
    authorised: Authorised,
    permission_key: str,
    payload: dict[str, Any],
    reason: str,
    clock: Clock,
) -> ApprovalOutcome:
    """Runs the action now when the person may, else files it for dual approval."""
    if authorised.grant.requires_approval:
        approval_id = await request_approval(
            db,
            permission_key=permission_key,
            requested_by=authorised.user.id,
            payload=payload,
            reason=reason,
            clock=clock,
        )
        return ApprovalOutcome(approval_id=approval_id, status="pending")
    await _HANDLERS[permission_key](db, payload, authorised.user.id, None)
    return ApprovalOutcome(approval_id=None, status="done")


async def decide(
    db: AsyncSession, *, request_id: UUID, decided_by: UUID, approve: bool, clock: Clock
) -> ApprovalOutcome:
    """The caller commits. Concurrent decisions wait on the row lock: the second one finds the
    request no longer pending, so the action runs once (review point 4)."""
    now = clock.now()
    request = await repository.lock_approval(db, request_id)
    if request is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if request.status != "pending":
        raise AppError(ErrorCode.APPROVAL_NOT_PENDING, 409)
    if request.expires_at <= now:
        raise AppError(ErrorCode.APPROVAL_EXPIRED, 409)
    # Q17: someone else, holding the permission through one of their roles.
    if decided_by == request.requested_by:
        raise AppError(ErrorCode.FORBIDDEN, 403)
    if await effective_grant(db, decided_by, request.permission_key) is None:
        raise AppError(ErrorCode.FORBIDDEN, 403)
    status: Literal["approved", "rejected"] = "approved" if approve else "rejected"
    if approve:
        await _HANDLERS[request.permission_key](
            db, request.payload, request.requested_by, decided_by
        )
    await repository.decide_approval(
        db, approval_id=request_id, status=status, decided_by=decided_by, now=now
    )
    await record_audit(
        db,
        actor_type="staff",
        actor_id=request.requested_by,
        approver_id=decided_by,
        action=f"approval.{'approve' if approve else 'reject'}",
        target_type="approval_request",
        target_id=str(request_id),
    )
    return ApprovalOutcome(approval_id=request_id, status=status)


async def pending_for(db: AsyncSession, *, viewer: UUID, clock: Clock) -> list[Any]:
    return await repository.pending_approvals(db, viewer=viewer, now=clock.now())


async def expire_approvals(sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock) -> int:
    """Every 10 minutes: pending requests older than 24 hours become `expired`."""
    async with sessionmaker() as db:
        expired = await repository.expire_approvals(db, now=clock.now())
        await commit(db)
    return expired


# --- First action behind dual approval: staff roles (`staff_roles.manage`) -----------------


async def ensure_staff_account(db: AsyncSession, user_id: UUID) -> None:
    """Staff roles go to staff accounts only (Q18: distinct from customer accounts)."""
    if not await repository.is_staff_account(db, user_id):
        raise AppError(ErrorCode.NOT_FOUND, 404)


async def manage_staff_role(
    db: AsyncSession, payload: dict[str, Any], actor_id: UUID, approver_id: UUID | None
) -> None:
    user_id, role, grant = (
        UUID(payload["user_id"]),
        str(payload["role_key"]),
        bool(payload["grant"]),
    )
    await ensure_staff_account(db, user_id)
    if grant:
        changed = await repository.grant_role(db, user_id=user_id, role=role, granted_by=actor_id)
    else:
        changed = await repository.revoke_role(db, user_id=user_id, role=role)
    if changed:
        await record_audit(
            db,
            actor_type="staff",
            actor_id=actor_id,
            approver_id=approver_id,
            action=f"staff_role.{'grant' if grant else 'revoke'}",
            target_type="user",
            target_id=str(user_id),
            after={"role": role},
        )


register_approval_handler("staff_roles.manage", manage_staff_role)
