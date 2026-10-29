"""Embeddings of listings (P2-T11, ADR-0020, plan Q9). Never commits but `embed_listing` and
`reindex`, which are jobs.

A listing put online is embedded by the worker from its text: title, description, attributes
with their labels, brand (the main photo's caption joins with T06a). Its version is checked at
the write: a listing edited meanwhile keeps the embedding of its new text, made by its own
event. A failure never touches the listing: it stays online, without embedding, until the job
is tried again or the daily reindexing catches it."""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.core.email import JobQueue
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.adapters.embedder import Embedder, checked_vector
from trovelya.modules.catalog.service.reading import attributes_shown
from trovelya.shared.events import OutboxEvent, Subscription

logger = structlog.get_logger(__name__)

EMBED_JOB = "embed_listing_job"
REINDEX_BATCH = 100

Session = async_sessionmaker[AsyncSession]


async def listing_text(db: AsyncSession, listing_id: UUID) -> tuple[str, int] | None:
    """The text embedded and the listing's version; None once deleted."""
    row = await repository.embedding_source(db, listing_id)
    if row is None:
        return None
    lines = [row.title, row.description]
    for shown in await attributes_shown(db, row.category_id, row.attributes):
        lines.append(f"{shown['name']} : {shown['value_name'] or shown['value']}")
    if row.brand:
        lines.append(f"Marque : {row.brand}")
    return "\n".join(lines), int(row.version)


async def embed_listing(sessionmaker: Session, embedder: Embedder, listing_id: UUID) -> bool:
    """True when the embedding was stored. The provider is called outside any transaction."""
    async with sessionmaker() as db:
        source = await listing_text(db, listing_id)
    if source is None:
        return False
    text, version = source
    vector = checked_vector(await embedder.embed(text))
    async with sessionmaker() as db:
        stored = await repository.set_embedding(
            db, listing_id, vector=vector, model=embedder.model, version=version
        )
        await commit(db)
    return stored


async def reindex(sessionmaker: Session, embedder: Embedder, *, batch: int = REINDEX_BATCH) -> int:
    """Active listings without an embedding of the current model, a batch at a time; one that
    fails is logged and left for the next run. Returns how many were embedded."""
    done, after = 0, None
    while True:
        async with sessionmaker() as db:
            stale = await repository.stale_embeddings(
                db, model=embedder.model, after=after, limit=batch
            )
        for listing_id in stale:
            try:
                done += await embed_listing(sessionmaker, embedder, listing_id)
            except Exception:
                logger.exception("catalog.embedding_failed", listing_id=str(listing_id))
        if len(stale) < batch:
            return done
        after = stale[-1]


def catalog_subscriptions(queue: JobQueue) -> list[Subscription]:
    """A listing put online is embedded by a job (the provider is never called in the
    consumer's transaction)."""

    async def embed_published(db: AsyncSession, event: OutboxEvent) -> None:
        await queue.enqueue_job(EMBED_JOB, str(event.aggregate_id))

    return [Subscription("catalog.embed_published", "listing.published", embed_published)]
