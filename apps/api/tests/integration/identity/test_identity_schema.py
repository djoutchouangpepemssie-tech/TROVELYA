"""Identity and sign-in tables (P1-T01a, section 7.3 with gaps E5 to E7 of the P1 plan)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trovelya.shared.ids import new_id

_INSERT_USER = text(
    "INSERT INTO users (id, email, username, display_name)"
    " VALUES (:id, :email, :username, :display_name)"
)


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose work is always rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


async def _insert_user(conn: AsyncConnection, **overrides: Any) -> Any:
    values = {
        "id": new_id(),
        "email": f"{new_id().hex}@example.org",
        "username": f"u_{new_id().hex[:8]}",
        "display_name": "Membre",
    } | overrides
    await conn.execute(_INSERT_USER, values)
    return values["id"]


async def _fails(conn: AsyncConnection, statement: Any, params: dict[str, Any]) -> str:
    """Run a statement expected to fail inside a savepoint; return the error message."""
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(statement, params)
    await savepoint.rollback()
    return str(error.value)


@pytest.mark.parametrize("username", ["Ab", "ab", "a b", "arcel!", "x" * 31])
async def test_username_format_check_rejects(conn: AsyncConnection, username: str) -> None:
    message = await _fails(
        conn,
        _INSERT_USER,
        {"id": new_id(), "email": "f@example.org", "username": username, "display_name": "M"},
    )
    assert "users_username_check" in message


async def test_username_format_check_accepts(conn: AsyncConnection) -> None:
    await _insert_user(conn, username="arcel.d_1")


async def test_email_citext_unique(conn: AsyncConnection) -> None:
    await _insert_user(conn, email="Arcel@Example.org")
    message = await _fails(
        conn,
        _INSERT_USER,
        {"id": new_id(), "email": "arcel@example.org", "username": "other", "display_name": "M"},
    )
    assert "users_email_key" in message


async def test_user_defaults(conn: AsyncConnection) -> None:
    user_id = await _insert_user(conn)
    row = (
        await conn.execute(
            text(
                "SELECT status, locale, timezone, country_code, visibility_factor, is_staff,"
                " marketing_opt_in, profile_completed_at, erasure_requested_at"
                " FROM users WHERE id = :id"
            ),
            {"id": user_id},
        )
    ).one()
    assert row.status == "active"
    assert (row.locale, row.timezone, row.country_code) == ("fr-FR", "Europe/Paris", "FR")
    assert float(row.visibility_factor) == 1.0
    assert (row.is_staff, row.marketing_opt_in) == (False, False)
    assert row.profile_completed_at is None and row.erasure_requested_at is None


@pytest.mark.parametrize("factor", ["-0.01", "1.01"])
async def test_visibility_factor_bounds(conn: AsyncConnection, factor: str) -> None:
    user_id = await _insert_user(conn)
    message = await _fails(
        conn,
        text("UPDATE users SET visibility_factor = CAST(:f AS numeric) WHERE id = :id"),
        {"f": factor, "id": user_id},
    )
    assert "users_visibility_factor_check" in message


async def test_display_name_and_bio_lengths(conn: AsyncConnection) -> None:
    user_id = await _insert_user(conn)
    assert "users_display_name_check" in await _fails(
        conn, text("UPDATE users SET display_name = '' WHERE id = :id"), {"id": user_id}
    )
    assert "users_bio_check" in await _fails(
        conn, text("UPDATE users SET bio = repeat('a', 501) WHERE id = :id"), {"id": user_id}
    )


async def test_users_updated_at_trigger(conn: AsyncConnection) -> None:
    user_id = await _insert_user(conn)
    await conn.execute(
        text("UPDATE users SET updated_at = now() - interval '1 day' WHERE id = :id"),
        {"id": user_id},
    )
    await conn.execute(text("UPDATE users SET bio = 'x' WHERE id = :id"), {"id": user_id})
    recent = await conn.scalar(
        text("SELECT updated_at > now() - interval '1 minute' FROM users WHERE id = :id"),
        {"id": user_id},
    )
    assert recent is True


_INSERT_MAGIC_LINK = text(
    "INSERT INTO magic_links (id, email, token_hash, purpose, expires_at)"
    " VALUES (:id, 'a@example.org', :hash, :purpose, now() + interval '15 minutes')"
)


@pytest.mark.parametrize("purpose", ["login", "verify_email", "change_email", "step_up"])
async def test_magic_link_purposes_accepted(conn: AsyncConnection, purpose: str) -> None:
    await conn.execute(
        _INSERT_MAGIC_LINK, {"id": new_id(), "hash": new_id().bytes, "purpose": purpose}
    )


async def test_magic_link_unknown_purpose_rejected(conn: AsyncConnection) -> None:
    message = await _fails(
        conn, _INSERT_MAGIC_LINK, {"id": new_id(), "hash": new_id().bytes, "purpose": "reset"}
    )
    assert "magic_links_purpose_check" in message


async def test_magic_link_token_hash_unique(conn: AsyncConnection) -> None:
    token_hash = new_id().bytes
    await conn.execute(_INSERT_MAGIC_LINK, {"id": new_id(), "hash": token_hash, "purpose": "login"})
    message = await _fails(
        conn, _INSERT_MAGIC_LINK, {"id": new_id(), "hash": token_hash, "purpose": "login"}
    )
    assert "magic_links_token_hash_key" in message


_INSERT_SESSION = text(
    "INSERT INTO sessions (id, user_id, token_hash, kind, expires_at, country_code)"
    " VALUES (:id, :user_id, :hash, :kind, now() + interval '30 days', :country)"
)


def _session(user_id: Any, kind: str = "web", country: str | None = None) -> dict[str, Any]:
    return {
        "id": new_id(),
        "user_id": user_id,
        "hash": new_id().bytes,
        "kind": kind,
        "country": country,
    }


async def test_session_kind_and_country(conn: AsyncConnection) -> None:
    user_id = await _insert_user(conn)
    await conn.execute(
        _INSERT_SESSION,
        _session(user_id, country="FR"),
    )
    assert "sessions_kind_check" in await _fails(
        conn,
        _INSERT_SESSION,
        _session(user_id, kind="api"),
    )


async def test_session_requires_existing_user(conn: AsyncConnection) -> None:
    message = await _fails(
        conn,
        _INSERT_SESSION,
        _session(new_id()),
    )
    assert "sessions_user_id_fkey" in message


async def test_oauth_identity_unique_per_provider_subject(conn: AsyncConnection) -> None:
    user_id = await _insert_user(conn)
    insert = text(
        "INSERT INTO auth_identities (id, user_id, provider, provider_subject)"
        " VALUES (:id, :user_id, :provider, 'sub-1')"
    )
    await conn.execute(insert, {"id": new_id(), "user_id": user_id, "provider": "google"})
    assert "auth_identities_provider_provider_subject_key" in await _fails(
        conn, insert, {"id": new_id(), "user_id": user_id, "provider": "google"}
    )
    assert "auth_identities_provider_check" in await _fails(
        conn, insert, {"id": new_id(), "user_id": user_id, "provider": "github"}
    )


async def test_passkey_credential_unique(conn: AsyncConnection) -> None:
    user_id = await _insert_user(conn)
    insert = text(
        "INSERT INTO passkeys (id, user_id, credential_id, public_key)"
        " VALUES (:id, :user_id, :credential, 'pk')"
    )
    await conn.execute(insert, {"id": new_id(), "user_id": user_id, "credential": b"cred"})
    assert "passkeys_credential_id_key" in await _fails(
        conn, insert, {"id": new_id(), "user_id": user_id, "credential": b"cred"}
    )


async def test_foreign_keys_are_indexed(conn: AsyncConnection) -> None:
    """Section 7.1: every foreign key is indexed (leading column of some index)."""
    rows = await conn.execute(
        text(
            """
            SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f'
              AND c.conrelid::regclass::text IN ('auth_identities', 'passkeys', 'sessions')
              AND NOT EXISTS (
                SELECT 1 FROM pg_index i
                WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
              )
            """
        )
    )
    assert rows.all() == []
