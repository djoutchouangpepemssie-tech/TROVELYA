"""Moderation of a listing's photos at publication (P2-T05b2, section 8.17, plan Q38): a score
of 0.9 or more refuses the listing, 0.5 to 0.9 sends it to review; a photo left unclassified
(no classifier, or it failed) or already published by another member sends it to review."""

import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_drafts import Session, create, draft, seller
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from trovelya.shared.ids import new_id


async def _publish_with(
    client: AsyncClient, sessionmaker: Session, moderation: dict[str, Any]
) -> dict[str, Any]:
    account, zone, media = await seller(sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE media SET moderation = CAST(:m AS jsonb) WHERE id = :id"),
            {"m": json.dumps(moderation), "id": media},
        )
        await db.commit()
    created = await create(client, account, draft(zone, [media]))
    assert created.status_code == 201, created.text
    published = await _call(client, account, created.json()["id"], "publish")
    assert published.status_code == 200, published.text
    return published.json()


def _scores(**scores: float) -> dict[str, Any]:
    clean = {"nudity": 0.0, "violence": 0.0, "weapons": 0.0, "drugs": 0.0}
    return {"classification": {"by": "fake", "scores": clean | scores}}


@pytest.mark.parametrize(
    ("score", "status", "outcome"),
    [(0.95, "removed", "refused"), (0.7, "pending_review", "review"), (0.3, "active", "online")],
)
async def test_image_thresholds(
    client: AsyncClient, sessionmaker: Session, score: float, status: str, outcome: str
) -> None:
    listing = await _publish_with(client, sessionmaker, _scores(weapons=score))
    assert (listing["status"], listing["moderation"]["outcome"]) == (status, outcome)
    if outcome != "online":
        assert listing["moderation"]["reasons"] == [
            {"code": "image_weapons", "label": "Image : armes"}
        ]


@pytest.mark.parametrize("moderation", [{}, {"classification": {"error": "failed"}}])
async def test_unclassified_photo_goes_to_review(
    client: AsyncClient, sessionmaker: Session, moderation: dict[str, Any]
) -> None:
    """Q38: no classifier configured, or it failed: a human looks, never online unchecked."""
    listing = await _publish_with(client, sessionmaker, moderation)
    assert listing["status"] == "pending_review"
    assert listing["moderation"]["reasons"] == [
        {"code": "image_unchecked", "label": "Image à vérifier par un humain"}
    ]


async def test_duplicate_image_goes_to_review(client: AsyncClient, sessionmaker: Session) -> None:
    listing = await _publish_with(client, sessionmaker, _scores() | {"duplicate_of": str(new_id())})
    assert listing["status"] == "pending_review"
    assert listing["moderation"]["reasons"] == [
        {"code": "duplicate_image", "label": "Photo déjà publiée par un autre membre"}
    ]


def test_thresholds_decide() -> None:
    """The setting's values, not constants: refused from `refuse`, reviewed from `review`."""
    from trovelya.modules.catalog.service.moderation import ImageThresholds, photos_verdict

    thresholds = ImageThresholds(refuse=0.6, review=0.4)
    photo = {"scores": {"nudity": 0.65, "violence": 0.45, "weapons": 0.0, "drugs": 0.0}}
    verdict = photos_verdict([photo], thresholds)
    assert (verdict.outcome, verdict.reasons) == ("refused", ("image_nudity", "image_violence"))


@pytest.mark.parametrize(
    "classification",
    [{"by": "x", "scores": {"hate": 0.99}}, {"by": "x", "scores": {"nudity": "0.95"}}, [1]],
)
async def test_unreadable_classification_goes_to_review(
    client: AsyncClient, sessionmaker: Session, classification: Any
) -> None:
    """Whatever is stored, a photo whose scores are not the four categories is reviewed."""
    listing = await _publish_with(client, sessionmaker, {"classification": classification})
    assert listing["status"] == "pending_review"
    assert listing["moderation"]["reasons"][0]["code"] == "image_unchecked"


@pytest.mark.parametrize(
    "thresholds",
    [
        {"refuse": 0.9},
        {"refuse": "0.9", "review": 0.5},
        {"refuse": 0.4, "review": 0.5},
        {"refuse": 1.5, "review": 0.5},
    ],
)
def test_invalid_thresholds_refused(thresholds: dict[str, Any]) -> None:
    from trovelya.modules.catalog.service.moderation import ImageThresholds

    with pytest.raises(ValueError):
        ImageThresholds.model_validate(thresholds)


def test_every_category_has_a_readable_reason() -> None:
    from trovelya.modules.catalog.service.moderation import label
    from trovelya.modules.media.adapters.classifier import CATEGORIES

    assert all(label(f"image_{c}").startswith("Image") for c in CATEGORIES)


async def test_renewed_listing_with_unclassified_photo_reviewed(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """Q32, Q38: putting back online checks the photos again."""
    account, zone, media = await seller(sessionmaker)
    created = await create(client, account, draft(zone, [media]))
    listing_id = created.json()["id"]
    assert (await _call(client, account, listing_id, "publish")).json()["status"] == "active"
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = 'expired' WHERE id = :l"), {"l": listing_id}
        )
        await db.execute(text("UPDATE media SET moderation = '{}' WHERE id = :m"), {"m": media})
        await db.commit()
    renewed = await _call(client, account, listing_id, "renew")
    assert renewed.json()["status"] == "pending_review", renewed.text


async def test_text_and_image_reasons_all_kept(client: AsyncClient, sessionmaker: Session) -> None:
    """Refused for the photo and reviewed for the text: the history keeps every reason."""
    account, zone, media = await seller(sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE media SET moderation = CAST(:m AS jsonb) WHERE id = :id"),
            {"m": json.dumps(_scores(nudity=0.95)), "id": media},
        )
        await db.commit()
    body = draft(zone, [media], description="Pistolet ancien de collection, belle patine.")
    created = await create(client, account, body)
    listing = (await _call(client, account, created.json()["id"], "publish")).json()
    assert [r["code"] for r in listing["moderation"]["reasons"]] == ["image_nudity", "weapons"]
