"""Named permissions, staff sessions and generic dual approval (P1-T11a, sections 3.1-3.2, Q17)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_profile import POLICY, T0, Account, make_account
from trovelya.core.errors import AppError
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.identity.service import create_session, expire_approvals
from trovelya.modules.identity.service.access import decide
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id


class Staff(Account):
    pass


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, clock: FixedClock
) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings())
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = clock
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


async def make_staff(
    sessionmaker: async_sessionmaker[AsyncSession],
    *roles: str,
    kind: str = "admin",
    strong: bool = True,
    clock: FixedClock | None = None,
) -> Staff:
    user_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, username, display_name, is_staff,"
                " email_verified_at, profile_completed_at, birth_year)"
                " VALUES (:id, :email, :u, 'Staff', true, now(), now(), 1985)"
            ),
            {
                "id": user_id,
                "email": f"staff_{user_id.hex}@example.org",
                "u": f"st_{user_id.hex[-10:]}",
            },
        )
        for role in roles:
            await db.execute(
                text("INSERT INTO user_roles (user_id, role_key) VALUES (:id, :r)"),
                {"id": user_id, "r": role},
            )
        issued = await create_session(
            db,
            user_id=user_id,
            kind=kind,  # pyright: ignore[reportArgumentType]
            ip="203.0.113.10",
            user_agent=None,
            country="FR",
            strong=strong,
            policy=POLICY,
            clock=clock or FixedClock(T0),
        )
        await db.commit()
    return Staff(user_id, f"staff_{user_id.hex}@example.org", issued.token)


async def _roles(sessionmaker: async_sessionmaker[AsyncSession], user_id: UUID) -> set[str]:
    async with sessionmaker() as db:
        rows = await db.scalars(
            text("SELECT role_key FROM user_roles WHERE user_id = :id"), {"id": user_id}
        )
        return set(rows.all())


async def _request_role(
    client: AsyncClient, requester: Staff, target: UUID, role: str = "staff_moderator"
) -> str:
    response = await client.post(
        "/v1/staff/roles/requests",
        headers=requester.headers,
        json={"user_id": str(target), "role_key": role, "grant": True, "reason": "Renfort"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pending"
    return str(body["approval_id"])


async def test_dual_approval_grants_the_role(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    approver = await make_staff(sessionmaker, "staff_superadmin")
    target = await make_staff(sessionmaker)
    approval_id = await _request_role(client, requester, target.id)
    assert await _roles(sessionmaker, target.id) == set()  # nothing before the approval

    listed = (await client.get("/v1/staff/approvals", headers=approver.headers)).json()["data"]
    mine = next(a for a in listed if a["id"] == approval_id)
    assert mine["permission_key"] == "staff_roles.manage" and mine["requested_by"] == str(
        requester.id
    )

    approved = await client.post(
        f"/v1/staff/approvals/{approval_id}/approve", headers=approver.headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert await _roles(sessionmaker, target.id) == {"staff_moderator"}


async def test_reject_does_nothing(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    approver = await make_staff(sessionmaker, "staff_superadmin")
    target = await make_staff(sessionmaker)
    approval_id = await _request_role(client, requester, target.id)
    rejected = await client.post(
        f"/v1/staff/approvals/{approval_id}/reject", headers=approver.headers
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert await _roles(sessionmaker, target.id) == set()
    again = await client.post(
        f"/v1/staff/approvals/{approval_id}/approve", headers=approver.headers
    )
    assert again.status_code == 409 and again.json()["code"] == "approval_not_pending"


async def test_require_permission_403(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    support = await make_staff(sessionmaker, "staff_support")
    target = await make_staff(sessionmaker)
    response = await client.post(
        "/v1/staff/roles/requests",
        headers=support.headers,
        json={
            "user_id": str(target.id),
            "role_key": "staff_moderator",
            "grant": True,
            "reason": "x",
        },
    )
    assert response.status_code == 403 and response.json()["code"] == "forbidden"


async def test_member_calling_staff_route_403(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    member = await make_account(sessionmaker, completed=True)
    assert (await client.get("/v1/staff/approvals", headers=member.headers)).status_code == 403
    assert (await client.get("/v1/staff/approvals")).status_code == 401


async def test_staff_route_requires_admin_session_and_recent_mfa(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    web_session = await make_staff(sessionmaker, "staff_superadmin", kind="web")
    response = await client.get("/v1/staff/approvals", headers=web_session.headers)
    assert response.status_code == 403 and response.json()["code"] == "forbidden"
    weak = await make_staff(sessionmaker, "staff_superadmin", strong=False)
    response = await client.get("/v1/staff/approvals", headers=weak.headers)
    assert response.status_code == 403 and response.json()["code"] == "step_up_required"


async def test_approval_by_requester_forbidden(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    target = await make_staff(sessionmaker)
    approval_id = await _request_role(client, requester, target.id)
    response = await client.post(
        f"/v1/staff/approvals/{approval_id}/approve", headers=requester.headers
    )
    assert response.status_code == 403
    assert await _roles(sessionmaker, target.id) == set()


async def test_approver_must_hold_permission(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    admin = await make_staff(sessionmaker, "staff_admin")  # no staff_roles.manage
    target = await make_staff(sessionmaker)
    approval_id = await _request_role(client, requester, target.id)
    response = await client.post(
        f"/v1/staff/approvals/{approval_id}/approve", headers=admin.headers
    )
    assert response.status_code == 403
    # Not listed either: they cannot act on it.
    listed = (await client.get("/v1/staff/approvals", headers=admin.headers)).json()["data"]
    assert approval_id not in [a["id"] for a in listed]


async def test_expired_approval_rejected(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    target = await make_staff(sessionmaker)
    approval_id = await _request_role(client, requester, target.id)
    clock.advance(timedelta(hours=24, seconds=1))
    # A fresh approver: admin sessions last 12 hours.
    approver = await make_staff(sessionmaker, "staff_superadmin", clock=clock)
    response = await client.post(
        f"/v1/staff/approvals/{approval_id}/approve", headers=approver.headers
    )
    assert response.status_code == 409 and response.json()["code"] == "approval_expired"
    assert await expire_approvals(sessionmaker, clock=clock) >= 1
    async with sessionmaker() as db:
        status = await db.scalar(
            text("SELECT status FROM approval_requests WHERE id = :id"), {"id": UUID(approval_id)}
        )
    assert status == "expired"
    assert await _roles(sessionmaker, target.id) == set()


async def test_concurrent_approvals_execute_once(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, clock: FixedClock
) -> None:
    """Review point 4: two approvers at the same time, the action runs once."""
    requester = await make_staff(sessionmaker, "staff_superadmin")
    first = await make_staff(sessionmaker, "staff_superadmin")
    second = await make_staff(sessionmaker, "staff_superadmin")
    target = await make_staff(sessionmaker)
    approval_id = UUID(await _request_role(client, requester, target.id))

    async def approve(approver: Staff) -> str:
        async with sessionmaker() as db:
            try:
                outcome = await decide(
                    db, request_id=approval_id, decided_by=approver.id, approve=True, clock=clock
                )
            except AppError as exc:
                await db.rollback()
                return exc.code
            await db.commit()
            return outcome.status

    results = sorted(await asyncio.gather(approve(first), approve(second)))
    assert results == ["approval_not_pending", "approved"]
    async with sessionmaker() as db:
        audits = await db.scalar(
            text(
                "SELECT count(*) FROM audit_log WHERE action = 'staff_role.grant'"
                " AND target_id = :t"
            ),
            {"t": str(target.id)},
        )
    assert audits == 1


async def test_both_identities_audited(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    approver = await make_staff(sessionmaker, "staff_superadmin")
    target = await make_staff(sessionmaker)
    approval_id = await _request_role(client, requester, target.id)
    await client.post(f"/v1/staff/approvals/{approval_id}/approve", headers=approver.headers)
    async with sessionmaker() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT action, actor_id, approver_id FROM audit_log"
                    " WHERE target_id IN (:a, :t) ORDER BY id"
                ),
                {"a": approval_id, "t": str(target.id)},
            )
        ).all()
    assert [(r.action, r.actor_id, r.approver_id) for r in rows] == [
        ("approval.request", requester.id, None),
        ("staff_role.grant", requester.id, approver.id),
        ("approval.approve", requester.id, approver.id),
    ]


@pytest.mark.parametrize(
    "change",
    [{"role_key": "member"}, {"role_key": "inconnu"}, {"reason": ""}],
)
async def test_invalid_role_request_422(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, change: dict[str, Any]
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    target = await make_staff(sessionmaker)
    body = {"user_id": str(target.id), "role_key": "staff_moderator", "grant": True, "reason": "x"}
    response = await client.post(
        "/v1/staff/roles/requests", headers=requester.headers, json={**body, **change}
    )
    assert response.status_code == 422


async def test_staff_roles_only_for_staff_accounts(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    requester = await make_staff(sessionmaker, "staff_superadmin")
    member = await make_account(sessionmaker, completed=True)
    for target in (member.id, new_id()):
        response = await client.post(
            "/v1/staff/roles/requests",
            headers=requester.headers,
            json={
                "user_id": str(target),
                "role_key": "staff_moderator",
                "grant": True,
                "reason": "x",
            },
        )
        assert response.status_code == 404
