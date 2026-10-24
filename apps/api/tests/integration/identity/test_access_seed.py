"""Roles, named permissions and dual approval (P1-T01b, sections 3.1 and 3.2).

The matrix below is section 3.2 copied by hand. Encoding in `role_permissions`:
- allowed            → requires_approval = false, limit_minor = NULL
- 🔒 (dual approval)  → requires_approval = true
- "✅ ≤ 500 € · 🔒 > 500 €" → requires_approval = false, limit_minor = 50000 (cents): above the
  limit the action needs dual approval.
Object conditions ("if reported", "levels 1-2") belong to each phase's policies.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trovelya.shared.ids import new_id

ROLES = {
    "anonymous",
    "member",
    "seller_individual",
    "seller_business",
    "staff_moderator",
    "staff_support",
    "staff_trust",
    "staff_finance",
    "staff_admin",
    "staff_superadmin",
}

Grant = tuple[bool, int | None]
OK: Grant = (False, None)
APPROVAL: Grant = (True, None)
UP_TO_500: Grant = (False, 50000)


def _sellers(grant: Grant) -> dict[str, Grant]:
    return {"seller_individual": grant, "seller_business": grant}


MATRIX: dict[str, dict[str, Grant]] = {
    "listing.publish": _sellers(OK),
    "order.buy": {"member": OK} | _sellers(OK),
    "listing.remove_any": {
        "staff_moderator": OK,
        "staff_trust": OK,
        "staff_admin": OK,
        "staff_superadmin": OK,
    },
    "conversation.read_private": {
        "staff_moderator": OK,
        "staff_support": OK,
        "staff_trust": OK,
        "staff_superadmin": OK,
    },
    "dispute.resolve": {"staff_support": UP_TO_500, "staff_admin": OK, "staff_superadmin": OK},
    "refund.create": {
        "staff_support": APPROVAL,
        "staff_finance": UP_TO_500,
        "staff_superadmin": OK,
    },
    "sanction.apply": {
        "staff_moderator": OK,
        "staff_trust": OK,
        "staff_admin": OK,
        "staff_superadmin": OK,
    },
    "user.suspend": {
        "staff_trust": APPROVAL,
        "staff_admin": APPROVAL,
        "staff_superadmin": APPROVAL,
    },
    "payout.validate_manual": {"staff_finance": APPROVAL, "staff_superadmin": OK},
    "settings.update": {"staff_admin": APPROVAL, "staff_superadmin": OK},
    "staff_roles.manage": {"staff_superadmin": APPROVAL},
    "personal_data.export": {"staff_admin": APPROVAL, "staff_superadmin": APPROVAL},
}

SETTINGS = {
    "auth.magic_link_ttl_min": 15,
    "auth.step_up_max_age_h": 12,
    "retention.erasure_grace_days": 30,
    "retention.data_export_days": 7,
    "auth.min_signup_age": 15,
    "auth.min_trade_age": 18,
}


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


async def test_roles_seeded(conn: AsyncConnection) -> None:
    rows = await conn.execute(text("SELECT key, description FROM roles"))
    seeded = {row.key: row.description for row in rows}
    assert set(seeded) == ROLES
    assert all(seeded.values())


async def test_seed_matches_matrix(conn: AsyncConnection) -> None:
    rows = await conn.execute(
        text(
            "SELECT role_key, permission_key, requires_approval, limit_minor FROM role_permissions"
        )
    )
    seeded: dict[str, dict[str, Grant]] = {}
    for row in rows:
        seeded.setdefault(row.permission_key, {})[row.role_key] = (
            row.requires_approval,
            row.limit_minor,
        )
    assert seeded == MATRIX


async def test_every_permission_described(conn: AsyncConnection) -> None:
    rows = await conn.execute(text("SELECT key, description FROM permissions"))
    seeded = {row.key: row.description for row in rows}
    assert set(seeded) == set(MATRIX)
    assert all(seeded.values())


async def test_settings_seeded(conn: AsyncConnection) -> None:
    rows = await conn.execute(
        text("SELECT key, value FROM platform_settings WHERE key = ANY(:keys)"),
        {"keys": list(SETTINGS)},
    )
    assert {row.key: row.value for row in rows} == SETTINGS


async def _staff_user(conn: AsyncConnection) -> object:
    user_id = new_id()
    await conn.execute(
        text(
            "INSERT INTO users (id, email, username, display_name, is_staff)"
            " VALUES (:id, :email, :username, 'Staff', true)"
        ),
        {"id": user_id, "email": f"{user_id.hex}@example.org", "username": f"s_{user_id.hex[:8]}"},
    )
    return user_id


_INSERT_APPROVAL = text(
    "INSERT INTO approval_requests"
    " (id, permission_key, requested_by, payload, reason, status, decided_by, expires_at)"
    " VALUES (:id, :permission, :requested_by, '{}', 'motif', :status, :decided_by,"
    " now() + interval '24 hours')"
)


async def test_approval_decider_differs_check(conn: AsyncConnection) -> None:
    requester = await _staff_user(conn)
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(
            _INSERT_APPROVAL,
            {
                "id": new_id(),
                "permission": "staff_roles.manage",
                "requested_by": requester,
                "status": "approved",
                "decided_by": requester,
            },
        )
    await savepoint.rollback()
    assert "approval_requests_check" in str(error.value)


async def test_approval_status_and_permission_checked(conn: AsyncConnection) -> None:
    requester = await _staff_user(conn)
    for overrides, constraint in (
        ({"status": "done"}, "approval_requests_status_check"),
        ({"permission": "unknown.permission"}, "approval_requests_permission_key_fkey"),
    ):
        params = {
            "id": new_id(),
            "permission": "staff_roles.manage",
            "requested_by": requester,
            "status": "pending",
            "decided_by": None,
        } | overrides
        savepoint = await conn.begin_nested()
        with pytest.raises(DBAPIError) as error:
            await conn.execute(_INSERT_APPROVAL, params)
        await savepoint.rollback()
        assert constraint in str(error.value)


async def test_user_role_requires_known_role(conn: AsyncConnection) -> None:
    user_id = await _staff_user(conn)
    insert = text("INSERT INTO user_roles (user_id, role_key) VALUES (:user_id, :role)")
    await conn.execute(insert, {"user_id": user_id, "role": "staff_superadmin"})
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(insert, {"user_id": user_id, "role": "god"})
    await savepoint.rollback()
    assert "user_roles_role_key_fkey" in str(error.value)
