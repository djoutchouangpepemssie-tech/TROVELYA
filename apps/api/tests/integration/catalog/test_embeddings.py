"""Embeddings of listings (P2-T11, ADR-0020, plan Q9): computed by the worker when a listing
goes online, with the model's name; reindexed when the model changes; a failure never
touches the listing."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text as sql

from tests.conftest import make_settings
from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_review_queue import _listing  # pyright: ignore[reportPrivateUsage]
from trovelya.modules.catalog.adapters.embedder import (
    DIMENSION,
    FakeEmbedder,
    checked_vector,
    embedder_from_settings,
)
from trovelya.modules.catalog.service.embeddings import (
    EMBED_JOB,
    catalog_subscriptions,
    embed_listing,
    listing_text,
    reindex,
)
from trovelya.shared.events import OutboxEvent
from trovelya.shared.ids import new_id


class _Queue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


class _Failing(FakeEmbedder):
    async def embed(self, text: str) -> list[float]:
        raise TimeoutError


async def _stored(sessionmaker: Session, listing_id: str) -> tuple[Any, ...]:
    async with sessionmaker() as db:
        row = (
            await db.execute(
                sql(
                    "SELECT vector_dims(embedding), embedding_model, status::text"
                    " FROM listings WHERE id = :l"
                ),
                {"l": listing_id},
            )
        ).one()
    return tuple(row)


async def test_embedding_dimension_matches_model() -> None:
    vector = await FakeEmbedder().embed("Robe en lin bleue")
    assert len(checked_vector(vector)) == DIMENSION == 1024
    for wrong in ([0.0] * 768, [float("nan")] * DIMENSION):
        with pytest.raises(ValueError, match="1024"):
            checked_vector(wrong)


async def test_embedding_computed_on_publish(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """The event of a listing put online enqueues the job; the job stores the vector."""
    _, listing = await _listing(client, sessionmaker)
    queue = _Queue()
    [subscription] = catalog_subscriptions(queue)
    event = OutboxEvent(
        id=new_id(),
        type="listing.published",
        aggregate_type="listing",
        aggregate_id=UUID(listing["id"]),
        payload={},
        occurred_at=datetime.now(UTC),
    )
    async with sessionmaker() as db:
        await subscription.handler(db, event)
    assert queue.jobs == [(EMBED_JOB, (listing["id"],))]
    assert await embed_listing(sessionmaker, FakeEmbedder(), UUID(listing["id"]))
    assert await _stored(sessionmaker, listing["id"]) == (1024, "fake-words-v1", "active")
    async with sessionmaker() as db:
        source = await listing_text(db, UUID(listing["id"]))
    assert source is not None and "Robe en lin bleue" in source[0]


async def test_reindex_on_model_change(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    _, listing = await _listing(client, sessionmaker)
    await embed_listing(sessionmaker, FakeEmbedder(), UUID(listing["id"]))
    assert await reindex(sessionmaker, FakeEmbedder("fake-words-v2"), batch=2) >= 1
    assert (await _stored(sessionmaker, listing["id"]))[1] == "fake-words-v2"
    assert await reindex(sessionmaker, FakeEmbedder("fake-words-v2")) == 0  # nothing left


async def test_embedding_failure_does_not_block_publication(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    """A provider down: the listing stays online, without embedding, for a later try."""
    _, listing = await _listing(client, sessionmaker)
    with pytest.raises(TimeoutError):
        await embed_listing(sessionmaker, _Failing(), UUID(listing["id"]))
    assert await _stored(sessionmaker, listing["id"]) == (None, None, "active")
    assert await reindex(sessionmaker, _Failing("fake-failing")) == 0  # logged, not raised


async def test_stale_text_not_stored(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """The listing changed while its text was embedded: the old vector is not stored."""
    _, listing = await _listing(client, sessionmaker)

    class _Meanwhile(FakeEmbedder):
        async def embed(self, text: str) -> list[float]:
            async with sessionmaker() as db:
                await db.execute(
                    sql("UPDATE listings SET title = 'Robe en lin verte' WHERE id = :l"),
                    {"l": listing["id"]},
                )
                await db.commit()
            return await super().embed(text)

    assert not await embed_listing(sessionmaker, _Meanwhile(), UUID(listing["id"]))
    assert (await _stored(sessionmaker, listing["id"]))[1] is None


@pytest.mark.parametrize("environment", ["preview", "staging", "production"])
def test_fake_embedder_refused_outside_development(environment: str) -> None:
    assert embedder_from_settings(make_settings(embedder="none")) is None
    with pytest.raises(ValueError, match="EMBEDDER"):
        make_settings(env=environment, embedder="fake")
