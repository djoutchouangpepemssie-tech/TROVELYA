from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from tests.conftest import make_settings
from trovelya.main import create_app

PROBLEM_JSON = "application/problem+json"


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_ok(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_ready_503_when_redis_down() -> None:
    async def ok() -> None:
        return None

    async def down() -> None:
        raise ConnectionError("redis unreachable")

    app = create_app(make_settings(), readiness_checks={"database": ok, "redis": down})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/ready")
    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["code"] == "service_unavailable"
    assert "redis unreachable" not in response.text


async def test_unknown_route_problem_json(client: AsyncClient) -> None:
    response = await client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["type"] == "https://docs.trovelya.com/errors/not_found"
    assert body["status"] == 404
    assert body["code"] == "not_found"
    assert body["title"]
    assert body["request_id"].startswith("req_")
    assert body["instance"] == "/nope"


class _Payload(BaseModel):
    amount_minor: int


def _app_with_test_routes() -> AsyncClient:
    router = APIRouter()

    @router.post("/echo", operation_id="test_echo")
    async def echo(payload: _Payload) -> _Payload:  # pyright: ignore[reportUnusedFunction]
        return payload

    @router.get("/boom", operation_id="test_boom")
    async def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("secret internal detail")

    app = create_app(make_settings())
    app.include_router(router)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_validation_error_problem_json() -> None:
    async with _app_with_test_routes() as c:
        response = await c.post("/echo", json={"amount_minor": "abc"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["field"] == "amount_minor"


async def test_request_id_propagated(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-Id": "req_from_client"})
    assert response.headers["x-request-id"] == "req_from_client"


async def test_request_id_generated(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.headers["x-request-id"].startswith("req_")


async def test_internal_error_hides_details() -> None:
    async with _app_with_test_routes() as c:
        response = await c.get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
