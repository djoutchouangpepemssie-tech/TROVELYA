from typing import Annotated

from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from trovelya.core.db import get_uow
from trovelya.main import create_app

Uow = Annotated[AsyncSession, Depends(get_uow)]
INSERT = text(
    "INSERT INTO platform_settings (key, value, description) VALUES (:k, '1', 'uow test')"
)


def _client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncClient:
    router = APIRouter()

    @router.post("/ok/{key}", operation_id="test_uow_ok")
    async def ok(key: str, uow: Uow) -> None:  # pyright: ignore[reportUnusedFunction]
        await uow.execute(INSERT, {"k": key})

    @router.post("/fail/{key}", operation_id="test_uow_fail")
    async def fail(key: str, uow: Uow) -> None:  # pyright: ignore[reportUnusedFunction]
        await uow.execute(INSERT, {"k": key})
        raise RuntimeError("boom")

    app = create_app(make_settings())
    app.state.sessionmaker = sessionmaker
    app.include_router(router)
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    )


async def _exists(engine: AsyncEngine, key: str) -> bool:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT count(*) FROM platform_settings WHERE key = :k"), {"k": key}
        )
    return found == 1


async def test_uow_commits_on_success(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with _client(sessionmaker) as client:
        assert (await client.post("/ok/uow.commit")).status_code == 200
    assert await _exists(engine, "uow.commit")
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM platform_settings WHERE key = 'uow.commit'"))


async def test_uow_rolls_back_on_error(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with _client(sessionmaker) as client:
        assert (await client.post("/fail/uow.rollback")).status_code == 500
    assert not await _exists(engine, "uow.rollback")
