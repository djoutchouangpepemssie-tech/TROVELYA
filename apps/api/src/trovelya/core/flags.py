"""Feature flags (section 7.2): every module from P10 on ships behind one, off by default."""

import hashlib
import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

CACHE_PREFIX = "flag:"
DEFAULT_TTL_SECONDS = 60
_MISSING = "__missing__"


class FlagService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        defaults: dict[str, bool],
        ttl_s: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._defaults = defaults
        self._ttl_s = ttl_s

    @staticmethod
    def in_rollout(key: str, user_id: UUID, rollout_pct: int) -> bool:
        """Deterministic bucket in [0, 100): the same user always lands in the same bucket."""
        digest = hashlib.sha256(f"{user_id}:{key}".encode()).hexdigest()
        return int(digest, 16) % 100 < rollout_pct

    async def _load(self, key: str) -> dict[str, Any] | None:
        cached: bytes | str | None = await self._redis.get(CACHE_PREFIX + key)
        if cached is not None:
            data = json.loads(cached)
            return None if data == _MISSING else data
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT enabled, rollout_pct, allow_user_ids, countries"
                        " FROM feature_flags WHERE key = :key"
                    ),
                    {"key": key},
                )
            ).one_or_none()
        data = (
            None
            if row is None
            else {
                "enabled": row.enabled,
                "rollout_pct": row.rollout_pct,
                "allow_user_ids": [str(u) for u in row.allow_user_ids],
                "countries": list(row.countries),
            }
        )
        await self._redis.set(
            CACHE_PREFIX + key, json.dumps(_MISSING if data is None else data), ex=self._ttl_s
        )
        return data

    async def is_enabled(
        self, key: str, *, user_id: UUID | None = None, country: str | None = None
    ) -> bool:
        flag = await self._load(key)
        if flag is None:
            return self._defaults.get(key, False)
        if user_id is not None and str(user_id) in flag["allow_user_ids"]:
            return True
        if not flag["enabled"]:
            return False
        if flag["countries"] and country not in flag["countries"]:
            return False
        rollout_pct: int = flag["rollout_pct"]
        if rollout_pct >= 100:
            return True
        return user_id is not None and self.in_rollout(key, user_id, rollout_pct)
