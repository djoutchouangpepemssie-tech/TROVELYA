"""Business parameters (`platform_settings`, the [PARAM] values of the spec), cached in Redis.

Every change is written to the audit log; the cache entry is dropped only after commit, so a
rolled-back change never evicts the value still in force.
"""

import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import on_commit
from trovelya.shared.audit import record_audit

CACHE_PREFIX = "settings:"
DEFAULT_TTL_SECONDS = 60

_UPSERT = text(
    "INSERT INTO platform_settings (key, value, description, updated_by)"
    " VALUES (:key, :value, :description, :actor_id)"
    " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by"
).bindparams(bindparam("value", type_=JSONB))


class SettingNotFoundError(KeyError):
    pass


class SettingsService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        ttl_s: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._ttl_s = ttl_s

    async def get(self, key: str) -> Any:
        cached: bytes | str | None = await self._redis.get(CACHE_PREFIX + key)
        if cached is not None:
            return json.loads(cached)
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT value FROM platform_settings WHERE key = :key"), {"key": key}
                )
            ).one_or_none()
        if row is None:
            raise SettingNotFoundError(key)
        await self._redis.set(CACHE_PREFIX + key, json.dumps(row.value), ex=self._ttl_s)
        return row.value

    async def set(
        self,
        session: AsyncSession,
        key: str,
        value: Any,
        *,
        actor_id: UUID,
        reason: str,
        description: str | None = None,
    ) -> None:
        """Write a setting in the caller's transaction (no commit) and audit the change."""
        previous = (
            await session.execute(
                text(
                    "SELECT value, description FROM platform_settings WHERE key = :key FOR UPDATE"
                ),
                {"key": key},
            )
        ).one_or_none()
        if previous is None and not description:
            raise ValueError("a new setting needs a description")
        await session.execute(
            _UPSERT,
            {
                "key": key,
                "value": value,
                "description": description or previous.description,  # type: ignore[union-attr]
                "actor_id": actor_id,
            },
        )
        await record_audit(
            session,
            actor_type="staff",
            actor_id=actor_id,
            action="settings.update",
            target_type="platform_settings",
            target_id=key,
            reason=reason,
            before=None if previous is None else {"value": previous.value},
            after={"value": value},
        )

        async def invalidate() -> None:
            await self._redis.delete(CACHE_PREFIX + key)

        on_commit(session, invalidate)
