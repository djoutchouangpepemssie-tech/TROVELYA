"""Helpers for hand-written SQL migrations."""

from typing import Any

from alembic import op
from sqlalchemy.util import await_only


def execute_script(sql: str) -> None:
    """Run a multi-statement SQL script inside the current migration transaction.

    SQLAlchemy's asyncpg dialect prepares every statement, and a prepared statement holds a
    single command. asyncpg's own `execute` without arguments uses the simple query
    protocol, which accepts a full script (functions with $$ bodies included).
    """
    driver_connection: Any = op.get_bind().connection.driver_connection
    await_only(driver_connection.execute(sql))
