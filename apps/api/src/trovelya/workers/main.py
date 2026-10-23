"""arq worker. Run with: arq trovelya.workers.main.WorkerSettings"""

from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob

from trovelya.core.config import get_settings
from trovelya.core.db import make_engine, make_sessionmaker
from trovelya.core.idempotency import purge_idempotency_keys
from trovelya.core.logging import configure_logging
from trovelya.core.redis import make_redis
from trovelya.shared.clock import SystemClock
from trovelya.workers.outbox_relay import (
    RedisStreamPublisher,
    relay_outbox_batch,
    verify_audit_chain,
)

Context = dict[str, Any]
EVERY_SECOND = set(range(60))


async def startup(ctx: Context) -> None:
    settings = get_settings()
    configure_logging()
    engine = make_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["sessionmaker"] = make_sessionmaker(engine)
    ctx["redis_client"] = make_redis(settings.redis_url)
    ctx["clock"] = SystemClock()


async def shutdown(ctx: Context) -> None:
    await ctx["redis_client"].aclose()
    await ctx["engine"].dispose()


async def relay_outbox(ctx: Context) -> int:
    publisher = RedisStreamPublisher(ctx["redis_client"])
    total = 0
    while (
        published := await relay_outbox_batch(ctx["sessionmaker"], publisher, clock=ctx["clock"])
    ) > 0:
        total += published
    return total


async def audit_verify_chain_job(ctx: Context) -> int:
    return len(await verify_audit_chain(ctx["sessionmaker"]))


async def purge_idempotency_keys_job(ctx: Context) -> int:
    return await purge_idempotency_keys(ctx["sessionmaker"], clock=ctx["clock"])


class WorkerSettings:
    functions: ClassVar[list[Any]] = []
    cron_jobs: ClassVar[list[CronJob]] = [
        cron(relay_outbox, second=EVERY_SECOND, unique=True, timeout=30),
        cron(audit_verify_chain_job, hour=3, minute=0, unique=True, timeout=600),
        cron(purge_idempotency_keys_job, hour=4, minute=30, unique=True, timeout=600),
    ]
    on_startup = startup
    on_shutdown = shutdown
    timezone = ZoneInfo("Europe/Paris")
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
