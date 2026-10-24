import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

INSERT = text(
    "INSERT INTO audit_log (actor_type, action, target_type, target_id, reason)"
    " VALUES ('system', 'test.action', 'test', :target, :reason) RETURNING id"
)


async def _insert(conn: AsyncConnection, target: str, reason: str = "r") -> int:
    return (await conn.execute(INSERT, {"target": target, "reason": reason})).scalar_one()


async def _chain_ok(conn: AsyncConnection) -> bool:
    return bool(
        await conn.scalar(text("SELECT coalesce(bool_and(ok), true) FROM audit_verify_chain()"))
    )


async def test_audit_update_rejected(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        row_id = await _insert(conn, "upd")
    with pytest.raises(DBAPIError, match="append-only"):
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE audit_log SET reason = 'x' WHERE id = :id"), {"id": row_id}
            )


async def test_audit_delete_rejected(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        row_id = await _insert(conn, "del")
    with pytest.raises(DBAPIError, match="append-only"):
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": row_id})


async def test_audit_truncate_rejected(engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="append-only"):
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE audit_log"))


async def test_audit_chain_links(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        ids = [await _insert(conn, f"link-{i}") for i in range(3)]
        rows = (
            await conn.execute(
                text("SELECT id, prev_hash, hash FROM audit_log WHERE id = ANY(:ids) ORDER BY id"),
                {"ids": ids},
            )
        ).all()
    assert rows[1].prev_hash == rows[0].hash
    assert rows[2].prev_hash == rows[1].hash
    assert all(len(row.hash) == 32 for row in rows)


async def test_first_row_has_null_prev_hash(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await _insert(conn, "first")
        first = (
            await conn.execute(text("SELECT prev_hash FROM audit_log ORDER BY id LIMIT 1"))
        ).one()
    assert first.prev_hash is None


async def test_audit_chain_detects_tampering(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            row_id = await _insert(conn, "tamper")
            await _insert(conn, "after-tamper")
            assert await _chain_ok(conn)
            await conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_immutable"))
            await conn.execute(
                text("UPDATE audit_log SET reason = 'forged' WHERE id = :id"), {"id": row_id}
            )
            await conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_immutable"))
            broken = (
                (
                    await conn.execute(
                        text("SELECT id FROM audit_verify_chain() WHERE NOT ok ORDER BY id")
                    )
                )
                .scalars()
                .all()
            )
            assert broken and broken[0] == row_id
        finally:
            await trans.rollback()


async def test_concurrent_inserts_keep_single_chain(engine: AsyncEngine) -> None:
    async def insert_one(i: int) -> None:
        async with engine.begin() as conn:
            await _insert(conn, f"concurrent-{i}")

    await asyncio.gather(*(insert_one(i) for i in range(20)))
    async with engine.connect() as conn:
        duplicates = await conn.scalar(
            text(
                "SELECT count(*) FROM (SELECT prev_hash FROM audit_log WHERE prev_hash IS NOT NULL"
                " GROUP BY prev_hash HAVING count(*) > 1) d"
            )
        )
        assert duplicates == 0
        assert await _chain_ok(conn)
