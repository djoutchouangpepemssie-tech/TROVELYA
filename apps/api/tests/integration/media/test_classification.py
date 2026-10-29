"""A listing photo is classified when processed (P2-T05b2, plan Q38): the classifier gets the
re-encoded image only (no text, no metadata), its scores are kept on the media for the
moderation; an error, or no classifier configured, leaves the photo unclassified (reviewed by
a human at publication, never online unchecked)."""

import math
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from tests.conftest import make_settings
from tests.integration.identity.test_profile import make_account
from tests.integration.media.test_processing import Session, _media, _photo  # pyright: ignore[reportPrivateUsage]
from trovelya.modules.media.adapters.classifier import (
    CATEGORIES,
    FakeImageClassifier,
    classifier_from_settings,
    valid_scores,
)
from trovelya.modules.media.adapters.storage import MemoryStorage
from trovelya.modules.media.service.processing import process_media


class _Failing:
    name = "failing"

    async def classify(self, image: bytes, content_type: str) -> dict[str, float]:
        raise TimeoutError


class _Recording(FakeImageClassifier):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[bytes, str]] = []

    async def classify(self, image: bytes, content_type: str) -> dict[str, float]:
        self.seen.append((image, content_type))
        return await super().classify(image, content_type)


async def _moderation(sessionmaker: Session, media_id: UUID) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text("SELECT moderation FROM media WHERE id = :m"), {"m": media_id})


async def test_scores_kept_on_the_photo(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    owner = await make_account(sessionmaker)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    classifier = _Recording()
    assert await process_media(sessionmaker, storage, media_id, classifier=classifier) == "ready"
    moderation = await _moderation(sessionmaker, media_id)
    assert moderation["classification"] == {
        "by": "fake",
        "scores": {"nudity": 0.0, "violence": 0.0, "weapons": 0.0, "drugs": 0.0},
    }
    [(image, content_type)] = classifier.seen
    assert content_type == "image/webp"
    variants = [data for (bucket, _), (data, _) in storage.objects.items() if bucket == "variants"]
    assert image in variants  # a re-encoded variant, never the original


async def test_classifier_error_leaves_the_photo_unclassified(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    owner = await make_account(sessionmaker)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    assert await process_media(sessionmaker, storage, media_id, classifier=_Failing()) == "ready"
    assert (await _moderation(sessionmaker, media_id))["classification"] == {"error": "failed"}


async def test_no_classifier_leaves_the_photo_unclassified(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    owner = await make_account(sessionmaker)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    assert await process_media(sessionmaker, storage, media_id) == "ready"
    assert "classification" not in await _moderation(sessionmaker, media_id)


async def test_avatar_not_classified(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    owner = await make_account(sessionmaker)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo(), purpose="avatar")
    classifier = _Recording()
    assert await process_media(sessionmaker, storage, media_id, classifier=classifier) == "ready"
    assert classifier.seen == []


@pytest.mark.parametrize(("provider", "configured"), [("none", False), ("fake", True)])
def test_classifier_chosen_by_settings(provider: str, configured: bool) -> None:
    """Q38: no classifier unless configured; the fake one only where asked for (tests, dev)."""
    classifier = classifier_from_settings(make_settings(image_classifier=provider))
    assert (classifier is not None) is configured


@pytest.mark.parametrize("environment", ["preview", "staging", "production"])
def test_fake_classifier_refused_outside_development(environment: str) -> None:
    """Q38: deployed by mistake, the fake classifier (all 0) would let every listing through."""
    with pytest.raises(ValueError, match="IMAGE_CLASSIFIER"):
        make_settings(env=environment, image_classifier="fake")


class _Scores:
    name = "odd"

    def __init__(self, scores: Any) -> None:
        self.scores = scores

    async def classify(self, image: bytes, content_type: str) -> Any:
        return self.scores


CLEAN = dict.fromkeys(CATEGORIES, 0.0)
ODD = [{}, {"nudity": 0.1}, [0], *(CLEAN | {"drugs": v} for v in ("0", None, math.nan, True, 2))]


@pytest.mark.parametrize("odd", ODD)
def test_odd_scores_are_not_scores(odd: Any) -> None:
    """A missing category, a string, None, NaN, a boolean or out of range: no scores."""
    assert valid_scores(odd) is None


def test_unknown_category_dropped() -> None:
    given = {"nudity": 0.1, "violence": 0, "weapons": 0, "drugs": 0, "hate": 0.95}
    assert valid_scores(given) == {"nudity": 0.1, "violence": 0.0, "weapons": 0.0, "drugs": 0.0}


async def test_odd_scores_leave_the_photo_unclassified(sessionmaker: Session) -> None:
    storage = MemoryStorage()
    owner = await make_account(sessionmaker)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    assert await process_media(sessionmaker, storage, media_id, classifier=_Scores({})) == "ready"
    classification = (await _moderation(sessionmaker, media_id))["classification"]
    assert classification == {"error": "invalid_scores"}


async def test_slow_classifier_leaves_the_photo_unclassified(
    sessionmaker: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider that hangs costs the classification, never the photo."""
    import asyncio

    from trovelya.modules.media.service import processing

    class _Slow(FakeImageClassifier):
        async def classify(self, image: bytes, content_type: str) -> dict[str, float]:
            await asyncio.sleep(5)
            return {}

    monkeypatch.setattr(processing, "CLASSIFY_TIMEOUT_S", 0.05)
    storage = MemoryStorage()
    owner = await make_account(sessionmaker)
    media_id, _ = await _media(sessionmaker, storage, owner.id, _photo())
    assert await process_media(sessionmaker, storage, media_id, classifier=_Slow()) == "ready"
    assert (await _moderation(sessionmaker, media_id))["classification"] == {"error": "failed"}
