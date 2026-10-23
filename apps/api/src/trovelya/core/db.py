"""Database engine, sessions and the request unit of work (SQLAlchemy 2 async + asyncpg).

Rule (section 5.4): services never commit. The boundary (an HTTP route through `get_uow`,
or a job) owns the transaction: commit on success, rollback on error.
"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def get_uow(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one transaction per request, committed only if the route succeeds."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        await session.commit()
