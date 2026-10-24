from typing import Any

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from trovelya.core.db import Uow
from trovelya.main import create_app

INSERT = text(
    "INSERT INTO platform_settings (key, value, description) VALUES (:k, '1', 'uow test')"
)


def _app(sessionmaker: async_sessionmaker[AsyncSession]) -> Any:
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
    return app


def _client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=_app(sessionmaker), raise_app_exceptions=False),
        base_url="http://test",
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


async def test_uow_commits_before_the_response_is_sent(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """Read-your-writes: a client that got its answer must see the change on its next request."""
    app = _app(sessionmaker)
    seen_at_response_start: list[bool] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            seen_at_response_start.append(await _exists(engine, "uow.before_response"))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/ok/uow.before_response",
        "raw_path": b"/ok/uow.before_response",
        "query_string": b"",
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    await app(scope, receive, send)
    assert seen_at_response_start == [True]
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM platform_settings WHERE key = 'uow.before_response'"))
