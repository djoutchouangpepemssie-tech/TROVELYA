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


async def test_refusal_threshold_is_a_setting(client: AsyncClient, sessionmaker: Session) -> None:
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE platform_settings SET value = CAST(:v AS jsonb)"
                " WHERE key = 'moderation.image_thresholds'"
            ),
            {"v": json.dumps({"refuse": 0.6, "review": 0.4})},
        )
        await db.commit()
    try:
        listing = await _publish_with(client, sessionmaker, _scores(nudity=0.65))
        assert listing["status"] == "removed"
    finally:
        async with sessionmaker() as db:
            await db.execute(
                text(
                    "UPDATE platform_settings SET value = CAST(:v AS jsonb)"
                    " WHERE key = 'moderation.image_thresholds'"
                ),
                {"v": json.dumps({"refuse": 0.9, "review": 0.5})},
            )
            await db.commit()
