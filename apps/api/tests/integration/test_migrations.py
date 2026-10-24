import asyncio

from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.conftest import alembic_config

REQUIRED_EXTENSIONS = {
    "postgis",
    "vector",
    "pg_trgm",
    "unaccent",
    "citext",
    "btree_gist",
    "ltree",
    "h3",
    "h3_postgis",
}
SOCLE_TABLES = {
    "platform_settings",
    "feature_flags",
    "outbox_events",
    "processed_events",
    "idempotency_keys",
    "audit_log",
}
IDENTITY_TABLES = {"users", "auth_identities", "passkeys", "magic_links", "sessions"}


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return {row[0] for row in rows}


async def test_upgrade_downgrade_upgrade(engine: AsyncEngine, migrated_url: str) -> None:
    config = alembic_config(migrated_url)
    async with engine.connect() as conn:
        extensions = {r[0] for r in await conn.execute(text("SELECT extname FROM pg_extension"))}
    assert extensions >= REQUIRED_EXTENSIONS
    assert await _tables(engine) >= SOCLE_TABLES | IDENTITY_TABLES

    await asyncio.to_thread(command.downgrade, config, "base")
    assert not ((SOCLE_TABLES | IDENTITY_TABLES) & await _tables(engine))

    await asyncio.to_thread(command.upgrade, config, "head")
    assert await _tables(engine) >= SOCLE_TABLES | IDENTITY_TABLES


async def test_updated_at_trigger(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO platform_settings (key, value, description, updated_at)"
                " VALUES ('test.updated_at', '1', 'test', now() - interval '1 day')"
            )
        )
        await conn.execute(
            text("UPDATE platform_settings SET value = '2' WHERE key = 'test.updated_at'")
        )
        recent = await conn.scalar(
            text(
                "SELECT updated_at > now() - interval '1 minute'"
                " FROM platform_settings WHERE key = 'test.updated_at'"
            )
        )
        assert recent is True
        await conn.execute(text("DELETE FROM platform_settings WHERE key = 'test.updated_at'"))


async def test_idempotency_key_unique_with_null_user(engine: AsyncEngine) -> None:
    """ADR-0012: anonymous requests are stored and their keys are still unique."""
    insert = text(
        "INSERT INTO idempotency_keys (key, user_id, method, path, request_hash)"
        " VALUES ('k-anon', NULL, 'POST', '/x', 'h')"
    )
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(insert)
        try:
            await conn.execute(insert)
            raise AssertionError("duplicate anonymous key accepted")
        except Exception as exc:  # noqa: BLE001
            assert "idempotency_keys_key_user_uniq" in str(exc)
        finally:
            await trans.rollback()
