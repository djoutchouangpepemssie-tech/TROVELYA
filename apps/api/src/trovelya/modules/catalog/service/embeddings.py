"""Embeddings of listings (P2-T11, ADR-0020, plan Q9). Never commits but `embed_listing`,
`reindex` and `drop_embedding`, which are jobs or event handlers.

A listing online, whose seller is shown, is embedded by the worker from its text: title,
description, attributes with their labels, brand (the main photo's caption joins with T06a).
Nothing else ever leaves for the provider. The vector is stored only if the listing is still
online with the same text; it is dropped when the listing leaves the shop window. A failure
never touches the listing: the job is tried again, then the daily reindexing catches it."""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.core.email import JobQueue
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.adapters.embedder import Embedder, checked_vector
from trovelya.modules.catalog.service.reading import attributes_shown
from trovelya.modules.identity.service import shown_sellers
from trovelya.shared.events import OutboxEvent, Subscription

logger = structlog.get_logger(__name__)

EMBED_JOB = "embed_listing_job"
REINDEX_BATCH = 100
# Provider down: the reindexing stops rather than waiting for every listing's timeout.
MAX_CONSECUTIVE_FAILURES = 5

Session = async_sessionmaker[AsyncSession]


def _value(shown: dict[str, Any]) -> str:
    value = shown["value_name"] or shown["value"]
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    return f"{value} {shown['unit']}" if shown.get("unit") else str(value)


async def listing_text(db: AsyncSession, listing_id: UUID) -> str | None:
    """The text embedded; None unless the listing is online and its seller shown."""
    row = await repository.embedding_source(db, listing_id)
    if row is None or not await shown_sellers(db, [row.seller_id]):
        return None
    lines = [row.title, row.description]
    for shown in await attributes_shown(db, row.category_id, row.attributes):
        lines.append(f"{shown['name']} : {_value(shown)}")
    if row.brand:
        lines.append(f"Marque : {row.brand}")
    return "\n".join(lines)


async def embed_listing(sessionmaker: Session, embedder: Embedder, listing_id: UUID) -> bool:
    """True when the embedding was stored. The provider is called outside any transaction;
    the listing is read again before the write: still online, with the same text."""
    async with sessionmaker() as db:
        text = await listing_text(db, listing_id)
    if text is None:
        return False
    vector = checked_vector(await embedder.embed(text))
    async with sessionmaker() as db:
        await repository.lock_listing_status(db, listing_id)
        if await listing_text(db, listing_id) != text:
            return False  # changed or gone meanwhile: its own event embeds it again
        stored = await repository.set_embedding(db, listing_id, vector=vector, model=embedder.model)
        await commit(db)
    return stored


async def reindex(sessionmaker: Session, embedder: Embedder, *, batch: int = REINDEX_BATCH) -> int:
    """Active listings without an embedding of the current model, a batch at a time; one that
    fails is logged and left for the next run. Returns how many were embedded."""
    done, after, failures = 0, None, 0
    while True:
        async with sessionmaker() as db:
            stale = await repository.stale_embeddings(
                db, model=embedder.model, after=after, limit=batch
            )
        for listing_id in stale:
            try:
                done += await embed_listing(sessionmaker, embedder, listing_id)
                failures = 0
            except Exception:
                logger.exception("catalog.embedding_failed", listing_id=str(listing_id))
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("catalog.reindex_stopped", failures=failures)
                    return done
        if len(stale) < batch:
            return done
        after = stale[-1]


def catalog_subscriptions(queue: JobQueue, embedder: Embedder | None) -> list[Subscription]:
    """With an embedder: a listing put online is embedded by a job (never in the consumer's
    transaction), one leaving the shop window loses its vector. Without, nothing."""
    if embedder is None:
        return []

    async def embed_published(db: AsyncSession, event: OutboxEvent) -> None:
        job = f"embed:{event.id}"  # an event delivered twice enqueues one job
        await queue.enqueue_job(EMBED_JOB, str(event.aggregate_id), _job_id=job)

    async def drop_embedding(db: AsyncSession, event: OutboxEvent) -> None:
        await repository.drop_embedding(db, event.aggregate_id)

    return [
        Subscription("catalog.embed_published", "listing.published", embed_published),
        Subscription("catalog.unembed_withdrawn", "listing.withdrawn", drop_embedding),
        Subscription("catalog.unembed_sold", "listing.sold", drop_embedding),
    ]
