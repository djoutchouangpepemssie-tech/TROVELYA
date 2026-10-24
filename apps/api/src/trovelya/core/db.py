"""Database engine, sessions and the request unit of work (SQLAlchemy 2 async + asyncpg).

Rule (section 5.4): services never commit. The boundary (an HTTP route through `get_uow`,
or a job) owns the transaction: commit on success, rollback on error.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
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


AfterCommit = Callable[[], Awaitable[None]]
_AFTER_COMMIT_KEY = "trovelya.after_commit"


def on_commit(session: AsyncSession, callback: AfterCommit) -> None:
    """Run `callback` once this session's transaction is committed (never on rollback).

    Use for side effects that must not happen for a rolled-back change, such as cache
    invalidation. Callbacks run only when the boundary commits through `commit()`.
    """
    session.info.setdefault(_AFTER_COMMIT_KEY, []).append(callback)


async def commit(session: AsyncSession) -> None:
    """Commit, then run the `on_commit` callbacks. The only way boundaries should commit."""
    await session.commit()
    callbacks: list[AfterCommit] = session.info.pop(_AFTER_COMMIT_KEY, [])
    for callback in callbacks:
        await callback()


async def get_uow(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one transaction per request, committed only if the route succeeds."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
        except BaseException:
            session.info.pop(_AFTER_COMMIT_KEY, None)
            await session.rollback()
            raise
        await commit(session)


# `scope="function"`: the transaction commits before the response is sent. With the default
# scope FastAPI sends the response first, so a client could read stale data on its next
# request, or be told "success" for a commit that then fails.
Uow = Annotated[AsyncSession, Depends(get_uow, scope="function")]
