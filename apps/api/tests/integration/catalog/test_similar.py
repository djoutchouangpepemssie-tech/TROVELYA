"""Similar listings (P2-T11b, ADR-0020): the nearest active ones by cosine distance, of the
current model, in the same universe; never the seller's own, nor those of a seller the visitor
blocked or no longer shown."""

from typing import Any
from uuid import UUID

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text as sql

from tests.integration.catalog.test_categories_api import catalog_client
from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
    create,
    draft,
    seller,
)
from tests.integration.catalog.test_review_queue import _listing  # pyright: ignore[reportPrivateUsage]
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from tests.integration.identity.test_profile import make_account
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.adapters.embedder import FakeEmbedder
from trovelya.modules.catalog.repository import _SIMILAR  # pyright: ignore[reportPrivateUsage]
from trovelya.modules.catalog.service.embeddings import embed_listing
from trovelya.modules.catalog.service.similar import similar_listings
from trovelya.shared.ids import new_id

MODEL = FakeEmbedder().model


async def _embedded(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
    model: str = MODEL,
    **changes: Any,
) -> Any:
    account, listing = await _listing(client, sessionmaker, **changes)
    assert await embed_listing(sessionmaker, FakeEmbedder(model), UUID(listing["id"]))
    return account, listing


async def _sql(sessionmaker: Session, statement: str, **params: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(sql(statement), params)
        await db.commit()


async def _similar(
    sessionmaker: Session, listing_id: str, model: str | None, viewer: UUID | None = None
) -> list[str]:
    async with sessionmaker() as db:
        found = await similar_listings(
            db, listing_id=UUID(listing_id), viewer_id=viewer, model=model, media_public_url=None
        )
    return [str(item.id) for item in found]


async def test_similar_filters(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """Withdrawn, deleted, other universe, blocked seller, same seller, seller erasing,
    suspended or with an incomplete profile, other model: left out; the nearest first (the
    texts make the distances distinct)."""
    model = f"fake-{new_id()}"  # this test's listings only (the database is shared)
    seller, target = await _embedded(client, sessionmaker, model)
    near = (await _embedded(client, sessionmaker, model))[1]
    far = (await _embedded(client, sessionmaker, model, title="Robe rouge à pois"))[1]
    withdrawn_seller, withdrawn = await _embedded(client, sessionmaker, model)
    assert (await _call(client, withdrawn_seller, withdrawn["id"], "withdraw")).status_code == 200
    other_universe = (await _embedded(client, sessionmaker, model))[1]
    await _sql(
        sessionmaker,
        "UPDATE listings SET category_id = (SELECT id FROM categories WHERE NOT path <@ 'mode'"
        " ORDER BY path LIMIT 1) WHERE id = :l",
        l=other_universe["id"],
    )
    blocked_seller, blocked = await _embedded(
        client, sessionmaker, model, title="Robe en lin verte"
    )
    erasing_seller, _ = await _embedded(client, sessionmaker, model)
    await _sql(
        sessionmaker,
        "UPDATE users SET erasure_requested_at = now() WHERE id = :u",
        u=erasing_seller.id,
    )
    hidden = [(await _embedded(client, sessionmaker, model))[1]["id"] for _ in range(3)]
    for statement in (
        "UPDATE users SET status = 'suspended' WHERE id = (SELECT seller_id FROM listings"
        " WHERE id = :l)",
        "UPDATE users SET profile_completed_at = NULL WHERE id = (SELECT seller_id FROM listings"
        " WHERE id = :l)",
        "UPDATE listings SET deleted_at = now() WHERE id = :l",
    ):
        await _sql(sessionmaker, statement, l=hidden.pop())
    await _embedded(client, sessionmaker)  # the same text, another model
    own = (await _listing(client, sessionmaker))[1]
    await _sql(
        sessionmaker, "UPDATE listings SET seller_id = :u WHERE id = :l", u=seller.id, l=own["id"]
    )
    assert await embed_listing(sessionmaker, FakeEmbedder(model), UUID(own["id"]))
    viewer = await make_account(sessionmaker, completed=True)
    await _sql(
        sessionmaker,
        "INSERT INTO blocks (blocker_id, blocked_id) VALUES (:a, :b)",
        a=viewer.id,
        b=blocked_seller.id,
    )

    assert await _similar(sessionmaker, target["id"], model, viewer.id) == [near["id"], far["id"]]
    assert await _similar(sessionmaker, target["id"], model) == [
        near["id"],
        blocked["id"],
        far["id"],
    ]
    assert await _similar(sessionmaker, target["id"], None) == []  # no embedder
    assert await _similar(sessionmaker, target["id"], MODEL) == []  # not yet reindexed
    assert await _similar(sessionmaker, withdrawn["id"], model) == []
    async with sessionmaker() as db:  # withdrawn once its seller and universe were read
        assert not await repository.similar_listings(
            db,
            listing_id=UUID(withdrawn["id"]),
            seller_id=withdrawn_seller.id,
            universe="mode",
            model=model,
            viewer_id=None,
            limit=8,
        )


async def test_similar_on_listing_page(sessionmaker: Session, redis_client: Redis) -> None:
    """The listing page carries them (section 11.5), each with its cover and price."""
    async with await catalog_client(
        sessionmaker, redis_client, verticals=False, embedder="fake"
    ) as fake:
        title = f"Robe en lin {new_id().hex}"  # a word of its own: the nearest by far
        _, target = await _embedded(fake, sessionmaker, title=title)
        _, near = await _embedded(fake, sessionmaker, title=title)
        page = (await fake.get(f"/v1/listings/{target['id']}")).json()
        account, zone, media = await seller(sessionmaker)
        mine = (await create(fake, account, draft(zone, [media], title=title))).json()
        own = await fake.get(f"/v1/listings/{mine['id']}", headers=account.headers)
    assert own.json()["similar"] == []  # the seller's own draft
    item = page["similar"][0]
    assert target["id"] not in {i["id"] for i in page["similar"]}
    assert (item["id"], item["title"], item["price"]["amount_minor"]) == (
        near["id"],
        near["title"],
        2500,
    )
    assert set(item) == {"id", "short_id", "title", "price", "cover"}


async def test_similar_uses_hnsw_index(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    seller, target = await _embedded(client, sessionmaker)
    params = {
        "id": target["id"],
        "model": MODEL,
        "seller_id": seller.id,
        "universe": "mode",
        "viewer": None,
        "limit": 8,
    }
    async with sessionmaker() as db:
        # A small table: the planner may prefer reading every active listing (sequentially,
        # by another partial index, or by bitmap) and sorting. Forbid those to see whether the
        # HNSW index can serve the order, whatever else the shared database holds.
        for plan_kind in ("seqscan", "bitmapscan", "sort"):
            await db.execute(sql("SET LOCAL enable_" + plan_kind + " = off"))
        plan = "\n".join(await db.scalars(sql("EXPLAIN " + _SIMILAR.text), params))
    main = plan.split("SubPlan")[0]  # the media's subquery sorts by position
    assert "Index Scan using listings_embedding_hnsw_idx" in main, plan
    assert "Order By: (embedding <=>" in main and "Sort" not in main, plan
