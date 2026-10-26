"""arq worker. Run with: arq trovelya.workers.main.WorkerSettings"""

import asyncio
import socket
from typing import Any, ClassVar
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import structlog
from arq import cron, func
from arq.connections import RedisSettings
from arq.cron import CronJob

import trovelya.modules.media.service  # noqa: F401  # pyright: ignore[reportUnusedImport]  (GDPR exporter)
from trovelya.core.config import get_settings
from trovelya.core.db import make_engine, make_sessionmaker
from trovelya.core.email import make_email_sender
from trovelya.core.idempotency import purge_idempotency_keys
from trovelya.core.logging import configure_logging
from trovelya.core.observability import (
    configure_observability,
    outbox_oldest_unpublished_seconds,
    trace_engine,
)
from trovelya.core.redis import make_redis
from trovelya.modules.identity.service import (
    EXPORT_JOB,
    build_data_export,
    expire_approvals,
    identity_subscriptions,
    process_erasures,
    purge_expired_exports,
    purge_expired_magic_links,
)
from trovelya.modules.media.adapters.storage import storage_from_settings
from trovelya.modules.media.tasks import MAX_TRIES as MEDIA_MAX_TRIES
from trovelya.modules.media.tasks import (
    PROCESS_JOB,
    PROCESS_TIMEOUT_S,
    process_media_job,
    purge_media_job,
    recover_stuck_media_job,
)
from trovelya.shared.clock import SystemClock
from trovelya.workers.consumers import consume_events, ensure_group
from trovelya.workers.email_jobs import MAX_TRIES, deliver_email
from trovelya.workers.outbox_relay import (
    RedisStreamPublisher,
    oldest_unpublished_age_seconds,
    relay_outbox_batch,
    verify_audit_chain,
)

logger = structlog.get_logger(__name__)

Context = dict[str, Any]
EVERY_SECOND = set(range(60))


async def startup(ctx: Context) -> None:
    settings = get_settings()
    configure_logging()
    configure_observability(None, settings, service_name="trovelya-worker")
    engine = make_engine(settings.database_url)
    trace_engine(engine)
    ctx["engine"] = engine
    ctx["sessionmaker"] = make_sessionmaker(engine)
    ctx["redis_client"] = make_redis(settings.redis_url)
    ctx["clock"] = SystemClock()
    ctx["settings"] = settings
    ctx["storage"] = storage_from_settings(settings)
    # One image decoded at a time in this worker (memory); waiting happens outside the
    # 60 s given to each image.
    ctx["image_slot"] = asyncio.Semaphore(1)
    ctx["http"] = httpx.AsyncClient()
    ctx["email_sender"] = make_email_sender(settings, ctx["http"])
    # Handlers enqueue their e-mails on arq's own pool (ctx["redis"]).
    ctx["subscriptions"] = identity_subscriptions(ctx["redis"], settings)
    ctx["consumer_name"] = socket.gethostname()
    await ensure_group(ctx["redis_client"])


async def shutdown(ctx: Context) -> None:
    await ctx["http"].aclose()
    await ctx["redis_client"].aclose()
    await ctx["engine"].dispose()


async def relay_outbox(ctx: Context) -> int:
    publisher = RedisStreamPublisher(ctx["redis_client"])
    total = 0
    while (
        published := await relay_outbox_batch(ctx["sessionmaker"], publisher, clock=ctx["clock"])
    ) > 0:
        total += published
    outbox_oldest_unpublished_seconds.set(
        await oldest_unpublished_age_seconds(ctx["sessionmaker"], clock=ctx["clock"])
    )
    if total:
        logger.info("outbox_relayed", published=total)
    return total


async def consume_events_job(ctx: Context) -> int:
    return await consume_events(
        ctx["redis_client"],
        ctx["sessionmaker"],
        ctx["subscriptions"],
        consumer_name=ctx["consumer_name"],
    )


async def audit_verify_chain_job(ctx: Context) -> int:
    return len(await verify_audit_chain(ctx["sessionmaker"]))


async def purge_idempotency_keys_job(ctx: Context) -> int:
    return await purge_idempotency_keys(ctx["sessionmaker"], clock=ctx["clock"])


async def purge_magic_links_job(ctx: Context) -> int:
    return await purge_expired_magic_links(ctx["sessionmaker"], clock=ctx["clock"])


async def build_data_export_job(ctx: Context, request_id: str) -> bool:
    return await build_data_export(
        ctx["sessionmaker"],
        UUID(request_id),
        settings=ctx["settings"],
        clock=ctx["clock"],
        queue=ctx["redis"],
    )


async def expire_approvals_job(ctx: Context) -> int:
    return await expire_approvals(ctx["sessionmaker"], clock=ctx["clock"])


async def process_erasures_job(ctx: Context) -> int:
    return await process_erasures(ctx["sessionmaker"], clock=ctx["clock"])


async def purge_data_exports_job(ctx: Context) -> int:
    return await purge_expired_exports(ctx["sessionmaker"], clock=ctx["clock"])


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        func(deliver_email, max_tries=MAX_TRIES, timeout=60),
        func(build_data_export_job, name=EXPORT_JOB, max_tries=3, timeout=300),
        func(
            process_media_job,
            name=PROCESS_JOB,
            max_tries=MEDIA_MAX_TRIES,
            timeout=PROCESS_TIMEOUT_S,
        ),
    ]
    cron_jobs: ClassVar[list[CronJob]] = [
        cron(relay_outbox, second=EVERY_SECOND, unique=True, timeout=30),
        cron(consume_events_job, second=EVERY_SECOND, unique=True, timeout=30),
        cron(audit_verify_chain_job, hour=3, minute=0, unique=True, timeout=600),
        cron(recover_stuck_media_job, minute=set(range(5, 60, 10)), unique=True, timeout=600),
        cron(expire_approvals_job, minute=set(range(0, 60, 10)), unique=True, timeout=120),
        cron(process_erasures_job, hour=4, minute=0, unique=True, timeout=1800),
        cron(purge_idempotency_keys_job, hour=4, minute=30, unique=True, timeout=600),
        cron(purge_magic_links_job, hour=4, minute=45, unique=True, timeout=600),
        cron(purge_data_exports_job, hour=5, minute=0, unique=True, timeout=600),
        # Every hour (ADR-0019: a withdrawn photo leaves storage at once), so at 4:20 right
        # after the erasures of 4:00.
        cron(purge_media_job, minute=20, unique=True, timeout=1800),
    ]
    on_startup = startup
    on_shutdown = shutdown
    timezone = ZoneInfo("Europe/Paris")
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
