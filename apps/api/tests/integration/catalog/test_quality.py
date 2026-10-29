"""The quality score of a draft (P2-T07, plan Q42): computed and stored at each write, read by
the seller with the tips that would raise it."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_categories_api import (
    seeded,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_draft_edit import _draft, _patch  # pyright: ignore[reportPrivateUsage]
from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from trovelya.modules.catalog.service.listings import recompute_quality


async def _stored(sessionmaker: Session, listing_id: str) -> int:
    async with sessionmaker() as db:
        score = await db.scalar(
            text("SELECT quality_score FROM listings WHERE id = :l"), {"l": listing_id}
        )
    return int(score)


def _gain(listing: dict[str, Any], code: str) -> int:
    return next(tip["gain"] for tip in listing["quality"]["tips"] if tip["code"] == code)


async def test_quality_computed_with_tips(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    _, listing = await _draft(client, sessionmaker)
    quality = listing["quality"]
    assert 0 < quality["score"] < 100
    assert quality["score"] == await _stored(sessionmaker, listing["id"])
    gains = [tip["gain"] for tip in quality["tips"]]
    assert gains == sorted(gains, reverse=True)
    photos = next(tip for tip in quality["tips"] if tip["code"] == "photos")
    assert (photos["gain"], photos["count"]) == (25, 5)  # one photo of six
    attributes = [tip for tip in quality["tips"] if tip["code"] == "attribute"]
    assert all(tip["attribute"] and tip["label"] for tip in attributes)


async def test_quality_recomputed_on_patch(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    account, listing = await _draft(client, sessionmaker)
    before, gain = listing["quality"]["score"], _gain(listing, "description")
    response = await _patch(client, account, listing, {"description": "Robe portée. " * 25})
    assert response.status_code == 200, response.text
    after = response.json()["quality"]
    assert after["score"] == before + gain
    assert "description" not in [tip["code"] for tip in after["tips"]]
    assert after["score"] == await _stored(sessionmaker, listing["id"])


async def test_stored_score_follows_the_masked_text(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    """Contact details masked at publication (Q12) shorten the text: the score follows."""
    account, listing = await _draft(client, sessionmaker)
    long = "Robe portée deux fois, appelez-moi au 06 12 34 56 78. " + "Très bon état. " * 6
    edited = await _patch(client, account, listing, {"description": long})
    assert edited.status_code == 200, edited.text
    published = await _call(client, account, listing["id"], "publish")
    assert published.status_code == 200, published.text
    assert published.json()["quality"]["score"] == await _stored(sessionmaker, listing["id"])


async def test_recompute_quality_mends_a_stale_score(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    _, listing = await _draft(client, sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET quality_score = 0 WHERE id = :l"), {"l": listing["id"]}
        )
        assert await recompute_quality(db) >= 1
        await db.commit()
    assert await _stored(sessionmaker, listing["id"]) == listing["quality"]["score"]
