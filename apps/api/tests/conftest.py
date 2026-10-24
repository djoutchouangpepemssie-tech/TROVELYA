from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from trovelya.core.config import Settings
from trovelya.core.health import ReadinessCheck
from trovelya.main import create_app

TEST_SECRET = "s" * 64
TEST_PROXY_SECRET = "p" * 48
TEST_FIELD_KEY = "e" * 64


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "database_url": "postgresql+asyncpg://test:test@localhost:5432/test",
        "redis_url": "redis://localhost:6379/0",
        "secret_key": TEST_SECRET,
        "proxy_shared_secret": TEST_PROXY_SECRET,
        "field_encryption_key": TEST_FIELD_KEY,
        "web_origin": "http://localhost:3000",
        "admin_origin": "http://localhost:3001",
    }
    values.update(overrides)
    return Settings.model_validate(values)


async def _ok() -> None:
    return None


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def readiness_checks() -> dict[str, ReadinessCheck]:
    return {"database": _ok, "redis": _ok}


@pytest.fixture
async def client(
    settings: Settings, readiness_checks: dict[str, ReadinessCheck]
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings, readiness_checks=readiness_checks)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
