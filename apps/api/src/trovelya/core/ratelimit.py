"""Sliding-window rate limits in Redis (section 11.4).

If Redis is unavailable the request is let through and the failure is logged: an outage of
the limiter must not take the site down (choice recorded in docs/plans/P0-fondations.md).
"""

import hashlib
import hmac
import math
import time
from uuid import uuid4

import structlog
from redis.asyncio import Redis
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from trovelya.core.client_ip import client_ip
from trovelya.core.errors import ErrorCode, problem_response

logger = structlog.get_logger(__name__)

EXEMPT_PATHS = frozenset({"/health", "/ready"})

# Returns {allowed, retry_after_ms}. Atomic: trims the window, counts, then records the hit.
_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
if redis.call('ZCARD', key) < limit then
  redis.call('ZADD', key, now, ARGV[4])
  redis.call('PEXPIRE', key, window)
  return {1, 0}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
return {0, tonumber(oldest[2]) + window - now}
"""


async def hit(redis: Redis, key: str, *, limit: int, window_s: int) -> int | None:
    """Record one hit. Returns None if allowed, else the seconds to wait before retrying."""
    now_ms = int(time.time() * 1000)
    allowed, retry_ms = await redis.eval(  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType, reportUnknownVariableType]
        _SLIDING_WINDOW, 1, f"rl:{key}", str(now_ms), str(window_s * 1000), str(limit), uuid4().hex
    )
    if allowed:
        return None
    return max(1, math.ceil(int(retry_ms) / 1000))  # pyright: ignore[reportUnknownArgumentType]


def client_fingerprint(ip: str, *, secret: str) -> str:
    """Keyed hash of the client IP: Redis keys and telemetry never hold the address itself."""
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


class AnonymousRateLimitMiddleware:
    """Default limit per client IP for every request (authenticated limits arrive in P1)."""

    def __init__(self, app: ASGIApp, *, per_minute: int, secret: str, proxy_secret: str) -> None:
        self.app = app
        self.per_minute = per_minute
        self._secret = secret
        self._proxy_secret = proxy_secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        ip = client_ip(scope, proxy_secret=self._proxy_secret)
        try:
            redis: Redis = scope["app"].state.redis
            key = f"anon:{client_fingerprint(ip, secret=self._secret)}"
            retry_after = await hit(redis, key, limit=self.per_minute, window_s=60)
        except Exception as exc:  # noqa: BLE001 — fail open, see module docstring
            logger.warning("ratelimit.redis_unavailable", error=type(exc).__name__)
            retry_after = None
        if retry_after is None:
            await self.app(scope, receive, send)
            return
        response = problem_response(
            Request(scope), ErrorCode.RATE_LIMITED, 429, headers={"Retry-After": str(retry_after)}
        )
        await response(scope, receive, send)
