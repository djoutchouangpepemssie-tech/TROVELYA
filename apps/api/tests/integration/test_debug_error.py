from httpx import ASGITransport, AsyncClient

from tests.conftest import make_settings
from trovelya.main import create_app


async def _get(env: str, path: str) -> int:
    app = create_app(make_settings(env=env), readiness_checks={})
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return (await client.get(path)).status_code


async def test_debug_error_route_absent_in_production() -> None:
    assert await _get("production", "/v1/_debug/error") == 404


async def test_debug_error_route_raises_outside_production() -> None:
    assert await _get("staging", "/v1/_debug/error") == 500
