"""HTTP idempotency keys, rate limits and CSRF (sections 11.1 and 11.4)."""

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from trovelya.core.csrf import CSRF_COOKIE, SESSION_COOKIE, issue_csrf_token
from trovelya.main import create_app

PROBLEM_JSON = "application/problem+json"
SECRET = "s" * 64


def _client(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, **settings: object
) -> AsyncClient:
    app = create_app(make_settings(**settings))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    )


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> AsyncIterator[AsyncClient]:
    async with _client(sessionmaker, redis_client) as c:
        yield c


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


# --- Idempotency -------------------------------------------------------------------------


async def test_missing_key_400(client: AsyncClient) -> None:
    response = await client.post("/v1/_test/echo", json={"a": 1})
    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "idempotency_key_required"


async def test_malformed_key_400(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/_test/echo", json={"a": 1}, headers={"Idempotency-Key": "not-a-uuid"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_invalid"


async def test_replay_same_response(client: AsyncClient) -> None:
    headers = _key()
    first = await client.post("/v1/_test/echo", json={"a": 1}, headers=headers)
    second = await client.post("/v1/_test/echo", json={"a": 1}, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["execution"] == second.json()["execution"]
    assert "idempotent-replayed" not in first.headers
    assert second.headers["idempotent-replayed"] == "true"


async def test_same_key_different_body_409(client: AsyncClient) -> None:
    headers = _key()
    await client.post("/v1/_test/echo", json={"a": 1}, headers=headers)
    response = await client.post("/v1/_test/echo", json={"a": 2}, headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"


async def test_same_key_other_path_409(client: AsyncClient) -> None:
    headers = _key()
    await client.post("/v1/_test/echo", json={"a": 1}, headers=headers)
    response = await client.post("/v1/_test/echo-other", json={"a": 1}, headers=headers)
    assert response.status_code == 409


async def test_json_key_order_does_not_matter(client: AsyncClient) -> None:
    headers = _key()
    first = await client.post(
        "/v1/_test/echo",
        content=b'{"a": 1, "b": 2}',
        headers={**headers, "content-type": "application/json"},
    )
    second = await client.post(
        "/v1/_test/echo",
        content=b'{"b":2,"a":1}',
        headers={**headers, "content-type": "application/json"},
    )
    assert second.status_code == 201
    assert second.json() == first.json()


async def test_concurrent_same_key_single_execution(client: AsyncClient) -> None:
    headers = _key()
    responses = await asyncio.gather(
        *(
            client.post("/v1/_test/echo?delay_ms=200", json={"a": 1}, headers=headers)
            for _ in range(3)
        )
    )
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409, 409]
    assert all(
        r.json()["code"] == "idempotency_in_progress" for r in responses if r.status_code == 409
    )


async def test_server_error_releases_key(client: AsyncClient) -> None:
    headers = _key()
    failed = await client.post("/v1/_test/echo?fail=1", json={"a": 1}, headers=headers)
    assert failed.status_code == 500
    retried = await client.post("/v1/_test/echo", json={"a": 1}, headers=headers)
    assert retried.status_code == 201


async def test_safe_methods_ignore_idempotency(client: AsyncClient) -> None:
    assert (await client.get("/health", headers={"Idempotency-Key": "x"})).status_code == 200


# --- Rate limit --------------------------------------------------------------------------


async def test_rate_limit_429_with_retry_after(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    async with _client(sessionmaker, redis_client, rate_limit_anonymous_per_minute=3) as c:
        statuses = [(await c.get("/v1/_test/ping")).status_code for _ in range(4)]
        limited = await c.get("/v1/_test/ping")
    assert statuses == [200, 200, 200, 429]
    assert limited.status_code == 429
    assert limited.headers["content-type"] == PROBLEM_JSON
    assert limited.json()["code"] == "rate_limited"
    assert 1 <= int(limited.headers["retry-after"]) <= 60


async def test_rate_limit_keys_on_trusted_client_ip(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    """Behind the web relay every request comes from Vercel: the relayed IP is the key."""

    def relayed(ip: str) -> dict[str, str]:
        return {"x-trv-proxy-secret": TEST_PROXY_SECRET, "x-trv-client-ip": ip}

    async with _client(sessionmaker, redis_client, rate_limit_anonymous_per_minute=2) as c:
        first = [(await c.get("/v1/_test/ping", headers=relayed("203.0.113.1"))).status_code]
        first += [(await c.get("/v1/_test/ping", headers=relayed("203.0.113.1"))).status_code]
        first += [(await c.get("/v1/_test/ping", headers=relayed("203.0.113.1"))).status_code]
        other = (await c.get("/v1/_test/ping", headers=relayed("203.0.113.2"))).status_code
    assert first == [200, 200, 429]
    assert other == 200


async def test_health_is_not_rate_limited(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    async with _client(sessionmaker, redis_client, rate_limit_anonymous_per_minute=1) as c:
        statuses = {(await c.get("/health")).status_code for _ in range(5)}
    assert statuses == {200}


async def test_rate_limit_fail_open_when_redis_down(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    broken = Redis.from_url("redis://127.0.0.1:1/0")  # pyright: ignore[reportUnknownMemberType]
    async with _client(sessionmaker, broken, rate_limit_anonymous_per_minute=1) as c:
        statuses = [(await c.get("/v1/_test/ping")).status_code for _ in range(3)]
    await broken.aclose()
    assert statuses == [200, 200, 200]


# --- CSRF --------------------------------------------------------------------------------


async def test_csrf_endpoint_sets_cookie(client: AsyncClient) -> None:
    response = await client.get("/v1/csrf")
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{CSRF_COOKIE}=")
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie or "SameSite=Lax" in cookie
    assert "HttpOnly" not in cookie
    assert response.json()["csrf_token"] in cookie


async def test_csrf_required_with_session_cookie(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/_test/echo", json={"a": 1}, headers={**_key(), "cookie": f"{SESSION_COOKIE}=abc"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


async def test_csrf_valid_token_accepted(client: AsyncClient) -> None:
    token = issue_csrf_token(SECRET)
    response = await client.post(
        "/v1/_test/echo",
        json={"a": 1},
        headers={
            **_key(),
            "cookie": f"{SESSION_COOKIE}=abc; {CSRF_COOKIE}={token}",
            "X-CSRF-Token": token,
        },
    )
    assert response.status_code == 201


async def test_csrf_bad_signature_403(client: AsyncClient) -> None:
    forged = issue_csrf_token("x" * 64)
    response = await client.post(
        "/v1/_test/echo",
        json={"a": 1},
        headers={
            **_key(),
            "cookie": f"{SESSION_COOKIE}=abc; {CSRF_COOKIE}={forged}",
            "X-CSRF-Token": forged,
        },
    )
    assert response.status_code == 403


async def test_csrf_header_must_match_cookie(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/_test/echo",
        json={"a": 1},
        headers={
            **_key(),
            "cookie": f"{SESSION_COOKIE}=abc; {CSRF_COOKIE}={issue_csrf_token(SECRET)}",
            "X-CSRF-Token": issue_csrf_token(SECRET),
        },
    )
    assert response.status_code == 403


async def test_csrf_not_required_without_session_cookie(client: AsyncClient) -> None:
    response = await client.post("/v1/_test/echo", json={"a": 1}, headers=_key())
    assert response.status_code == 201


async def test_test_routes_absent_in_production(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    async with _client(sessionmaker, redis_client, env="production") as c:
        assert (await c.get("/v1/_test/ping")).status_code == 404
