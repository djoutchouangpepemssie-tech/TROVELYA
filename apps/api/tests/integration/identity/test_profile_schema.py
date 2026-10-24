"""Profile, social and GDPR tables (P1-T01c, section 7.3 and gap E8 of the P1 plan)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trovelya.shared.ids import new_id

PROFILE_TABLES = (
    "addresses",
    "search_zones",
    "user_preferences",
    "consents",
    "follows",
    "blocks",
    "data_requests",
    "data_exports",
)


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


async def _user(conn: AsyncConnection) -> UUID:
    user_id = new_id()
    await conn.execute(
        text(
            "INSERT INTO users (id, email, username, display_name)"
            " VALUES (:id, :email, :username, 'Membre')"
        ),
        {"id": user_id, "email": f"{user_id.hex}@example.org", "username": f"u_{user_id.hex[-8:]}"},
    )
    return user_id


async def _fails(conn: AsyncConnection, sql: str, params: dict[str, Any]) -> str:
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(text(sql), params)
    await savepoint.rollback()
    return str(error.value)


_INSERT_ZONE = (
    "INSERT INTO search_zones (id, user_id, label, place_name, center, radius_m, is_default)"
    " VALUES (:id, :user_id, 'Maison', 'Lyon 7e',"
    " ST_SetSRID(ST_MakePoint(4.84, 45.74), 4326)::geography, :radius, :is_default)"
)


@pytest.mark.parametrize("radius", [1000, 2000, 5000, 10000, 25000, 50000, 100000])
async def test_zone_radius_allowed_values(conn: AsyncConnection, radius: int) -> None:
    user_id = await _user(conn)
    await conn.execute(
        text(_INSERT_ZONE),
        {"id": new_id(), "user_id": user_id, "radius": radius, "is_default": False},
    )


async def test_zone_radius_other_values_rejected(conn: AsyncConnection) -> None:
    user_id = await _user(conn)
    message = await _fails(
        conn,
        _INSERT_ZONE,
        {"id": new_id(), "user_id": user_id, "radius": 3000, "is_default": False},
    )
    assert "search_zones_radius_m_check" in message


async def test_single_default_zone(conn: AsyncConnection) -> None:
    user_id = await _user(conn)
    params = {"user_id": user_id, "radius": 5000, "is_default": True}
    await conn.execute(text(_INSERT_ZONE), {"id": new_id()} | params)
    message = await _fails(conn, _INSERT_ZONE, {"id": new_id()} | params)
    assert "search_zones_default_uniq" in message


_INSERT_ADDRESS = (
    "INSERT INTO addresses (id, user_id, full_name, line1, postal_code, city, country_code,"
    " is_default_shipping, deleted_at)"
    " VALUES (:id, :user_id, 'Arcel D.', '1 rue de la Paix', '69007', 'Lyon', 'FR',"
    " :is_default, :deleted_at)"
)


async def test_single_default_shipping_address(conn: AsyncConnection) -> None:
    user_id = await _user(conn)
    params = {"user_id": user_id, "is_default": True}
    # A deleted default address does not count.
    await conn.execute(
        text(_INSERT_ADDRESS),
        {"id": new_id(), "deleted_at": datetime(2026, 1, 1, tzinfo=UTC)} | params,
    )
    await conn.execute(text(_INSERT_ADDRESS), {"id": new_id(), "deleted_at": None} | params)
    message = await _fails(conn, _INSERT_ADDRESS, {"id": new_id(), "deleted_at": None} | params)
    assert "addresses_default_shipping_uniq" in message


async def test_preferences_defaults(conn: AsyncConnection) -> None:
    user_id = await _user(conn)
    await conn.execute(
        text("INSERT INTO user_preferences (user_id) VALUES (:user_id)"), {"user_id": user_id}
    )
    row = (
        await conn.execute(
            text(
                "SELECT interests, sizes, feed_discovery_level, personalised_feed,"
                " notification_settings FROM user_preferences WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        )
    ).one()
    assert (row.interests, row.sizes, row.feed_discovery_level) == ([], {}, 50)
    assert (row.personalised_feed, row.notification_settings) == (True, {})


async def test_feed_discovery_level_bounds(conn: AsyncConnection) -> None:
    user_id = await _user(conn)
    message = await _fails(
        conn,
        "INSERT INTO user_preferences (user_id, feed_discovery_level) VALUES (:user_id, 101)",
        {"user_id": user_id},
    )
    assert "user_preferences_feed_discovery_level_check" in message


_INSERT_CONSENT = (
    "INSERT INTO consents (id, user_id, anonymous_id, purpose, granted, policy_version, source)"
    " VALUES (:id, :user_id, :anonymous_id, :purpose, true, '2026-10', 'banner')"
)


async def test_consent_needs_a_subject_and_known_purpose(conn: AsyncConnection) -> None:
    await conn.execute(
        text(_INSERT_CONSENT),
        {"id": new_id(), "user_id": None, "anonymous_id": "anon-1", "purpose": "analytics"},
    )
    assert "consents_check" in await _fails(
        conn,
        _INSERT_CONSENT,
        {"id": new_id(), "user_id": None, "anonymous_id": None, "purpose": "analytics"},
    )
    assert "consents_purpose_check" in await _fails(
        conn,
        _INSERT_CONSENT,
        {"id": new_id(), "user_id": None, "anonymous_id": "anon-1", "purpose": "tracking"},
    )


async def test_follow_exactly_one_target(conn: AsyncConnection) -> None:
    follower, followee = await _user(conn), await _user(conn)
    sql = (
        "INSERT INTO follows (follower_id, followee_user_id, followee_shop_id)"
        " VALUES (:follower, :user, :shop)"
    )
    await conn.execute(text(sql), {"follower": follower, "user": followee, "shop": None})
    assert "follows_check" in await _fails(
        conn, sql, {"follower": follower, "user": followee, "shop": new_id()}
    )
    assert "follows_check" in await _fails(
        conn, sql, {"follower": follower, "user": None, "shop": None}
    )
    assert "follows_uniq" in await _fails(
        conn, sql, {"follower": follower, "user": followee, "shop": None}
    )
    assert "follows_not_self" in await _fails(
        conn, sql, {"follower": follower, "user": follower, "shop": None}
    )


async def test_cannot_block_self(conn: AsyncConnection) -> None:
    user_id = await _user(conn)
    message = await _fails(
        conn, "INSERT INTO blocks (blocker_id, blocked_id) VALUES (:id, :id)", {"id": user_id}
    )
    assert "blocks_check" in message


_INSERT_REQUEST = (
    "INSERT INTO data_requests (id, user_id, kind, status) VALUES (:id, :user_id, :kind, :status)"
)


async def test_single_pending_request_per_kind(conn: AsyncConnection) -> None:
    user_id = await _user(conn)
    await conn.execute(
        text(_INSERT_REQUEST),
        {"id": new_id(), "user_id": user_id, "kind": "export", "status": "completed"},
    )
    await conn.execute(
        text(_INSERT_REQUEST),
        {"id": new_id(), "user_id": user_id, "kind": "export", "status": "received"},
    )
    await conn.execute(
        text(_INSERT_REQUEST),
        {"id": new_id(), "user_id": user_id, "kind": "erasure", "status": "received"},
    )
    message = await _fails(
        conn,
        _INSERT_REQUEST,
        {"id": new_id(), "user_id": user_id, "kind": "export", "status": "processing"},
    )
    assert "data_requests_pending_uniq" in message


async def test_one_export_file_per_request(conn: AsyncConnection) -> None:
    user_id, request_id = await _user(conn), new_id()
    await conn.execute(
        text(_INSERT_REQUEST),
        {"id": request_id, "user_id": user_id, "kind": "export", "status": "completed"},
    )
    sql = (
        "INSERT INTO data_exports (id, data_request_id, ciphertext, expires_at)"
        " VALUES (:id, :request_id, '\\x00', now() + interval '7 days')"
    )
    await conn.execute(text(sql), {"id": new_id(), "request_id": request_id})
    assert "data_exports_data_request_id_key" in await _fails(
        conn, sql, {"id": new_id(), "request_id": request_id}
    )


async def test_profile_foreign_keys_are_indexed(conn: AsyncConnection) -> None:
    rows = await conn.execute(
        text(
            """
            SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f'
              AND c.conrelid::regclass::text = ANY(:tables)
              AND NOT EXISTS (
                SELECT 1 FROM pg_index i
                WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
              )
            """
        ),
        {"tables": list(PROFILE_TABLES)},
    )
    assert rows.all() == []
