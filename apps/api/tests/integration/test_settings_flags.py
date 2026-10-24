import pytest
from redis.asyncio import Redis
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.core.flags import FlagService
from trovelya.core.settings_service import SettingNotFoundError, SettingsService
from trovelya.shared.ids import new_id

STAFF = new_id()


@pytest.fixture
def settings_service(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> SettingsService:
    return SettingsService(sessionmaker, redis_client)


async def _set(
    service: SettingsService, sm: async_sessionmaker[AsyncSession], key: str, value: object
) -> None:
    async with sm() as session:
        await service.set(session, key, value, actor_id=STAFF, reason="test", description="test")
        await commit(session)


async def test_get_unknown_setting_raises(settings_service: SettingsService) -> None:
    with pytest.raises(SettingNotFoundError):
        await settings_service.get("does.not.exist")


async def test_get_cached(
    settings_service: SettingsService,
    sessionmaker: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
) -> None:
    await _set(settings_service, sessionmaker, "test.cached", {"bp": 500})
    assert await settings_service.get("test.cached") == {"bp": 500}

    statements: list[str] = []

    def count(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        assert await settings_service.get("test.cached") == {"bp": 500}
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)
    assert not [s for s in statements if "platform_settings" in s]


async def test_set_writes_audit(
    settings_service: SettingsService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _set(settings_service, sessionmaker, "test.audited", 1)
    await _set(settings_service, sessionmaker, "test.audited", 2)
    async with sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT actor_id, before, after FROM audit_log WHERE action = 'settings.update'"
                    " AND target_id = 'test.audited' ORDER BY id DESC LIMIT 1"
                )
            )
        ).one()
    assert row.actor_id == STAFF
    assert row.before == {"value": 1}
    assert row.after == {"value": 2}


async def test_cache_invalidated_only_after_commit(
    settings_service: SettingsService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _set(settings_service, sessionmaker, "test.invalidate", 1)
    assert await settings_service.get("test.invalidate") == 1

    async with sessionmaker() as session:
        await settings_service.set(session, "test.invalidate", 2, actor_id=STAFF, reason="r")
        await session.rollback()
    assert await settings_service.get("test.invalidate") == 1

    await _set(settings_service, sessionmaker, "test.invalidate", 3)
    assert await settings_service.get("test.invalidate") == 3


async def test_new_setting_requires_description(
    settings_service: SettingsService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker() as session:
        with pytest.raises(ValueError, match="description"):
            await settings_service.set(session, "test.nodesc", 1, actor_id=STAFF, reason="r")


async def _flag(sm: async_sessionmaker[AsyncSession], key: str, **columns: object) -> None:
    values: dict[str, object] = {
        "enabled": True,
        "rollout_pct": 100,
        "allow_user_ids": [],
        "countries": [],
    }
    values.update(columns)
    async with sm() as session:
        await session.execute(
            text(
                "INSERT INTO feature_flags (key, enabled, rollout_pct, allow_user_ids, countries)"
                " VALUES (:key, :enabled, :rollout_pct, :allow_user_ids, :countries)"
                " ON CONFLICT (key) DO UPDATE SET enabled = EXCLUDED.enabled,"
                " rollout_pct = EXCLUDED.rollout_pct, allow_user_ids = EXCLUDED.allow_user_ids,"
                " countries = EXCLUDED.countries"
            ),
            {"key": key, **values},
        )
        await session.commit()


@pytest.fixture
def flags(sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis) -> FlagService:
    return FlagService(sessionmaker, redis_client, defaults={"default_on": True})


async def test_unknown_flag_uses_default(flags: FlagService) -> None:
    assert await flags.is_enabled("default_on") is True
    assert await flags.is_enabled("never_defined") is False


async def test_disabled_flag(
    flags: FlagService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _flag(sessionmaker, "off_flag", enabled=False)
    assert await flags.is_enabled("off_flag", user_id=new_id()) is False


async def test_allow_list(
    flags: FlagService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    allowed = new_id()
    await _flag(sessionmaker, "beta", enabled=False, rollout_pct=0, allow_user_ids=[allowed])
    assert await flags.is_enabled("beta", user_id=allowed) is True
    assert await flags.is_enabled("beta", user_id=new_id()) is False


async def test_country_filter(
    flags: FlagService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _flag(sessionmaker, "fr_only", countries=["FR"])
    assert await flags.is_enabled("fr_only", user_id=new_id(), country="FR") is True
    assert await flags.is_enabled("fr_only", user_id=new_id(), country="BE") is False
    assert await flags.is_enabled("fr_only", user_id=new_id()) is False


async def test_rollout_deterministic(
    flags: FlagService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _flag(sessionmaker, "half", rollout_pct=50)
    user = new_id()
    first = await flags.is_enabled("half", user_id=user)
    assert all([await flags.is_enabled("half", user_id=user) == first for _ in range(100)])


async def test_rollout_without_user_needs_full_rollout(
    flags: FlagService, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _flag(sessionmaker, "partial", rollout_pct=99)
    assert await flags.is_enabled("partial") is False
    await _flag(sessionmaker, "full", rollout_pct=100)
    assert await flags.is_enabled("full") is True


def test_rollout_distribution() -> None:
    hits = sum(FlagService.in_rollout("thirty", new_id(), 30) for _ in range(10_000))
    assert 2800 <= hits <= 3200
