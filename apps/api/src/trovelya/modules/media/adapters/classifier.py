"""Image classification behind a protocol (P2-T05b2, 8.17, plan Q38, Q39): scores from 0 to 1
by an EU provider chosen before production, on the re-encoded image only (no text, no
metadata). None configured: photos unclassified, listings reviewed (Q38); the fake one is for
tests and local development."""

import math
from collections.abc import Mapping
from typing import Any, Protocol, cast

from trovelya.core.config import Settings

CATEGORIES = ("nudity", "violence", "weapons", "drugs")


class ImageClassifier(Protocol):
    name: str

    async def classify(self, image: bytes, content_type: str) -> dict[str, float]:
        """A score per category of `CATEGORIES`; raises when the provider fails."""
        ...


class FakeImageClassifier:
    """Gives the scores it was built with (all 0 by default), whatever the image."""

    name = "fake"

    def __init__(self, scores: Mapping[str, float] | None = None) -> None:
        self.scores = dict.fromkeys(CATEGORIES, 0.0) | dict(scores or {})

    async def classify(self, image: bytes, content_type: str) -> dict[str, float]:
        return dict(self.scores)


def valid_scores(raw: Any) -> dict[str, float] | None:
    """The four scores, as floats from 0 to 1, other categories dropped; None when one is
    missing or not a number (a string, a boolean, NaN, out of range): the photo is then
    unclassified, and reviewed by a human."""
    if not isinstance(raw, Mapping):
        return None
    given = cast(Mapping[str, Any], raw)
    scores: dict[str, float] = {}
    for category in CATEGORIES:
        value = given.get(category)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        score = float(value)
        if not math.isfinite(score) or not 0 <= score <= 1:
            return None
        scores[category] = score
    return scores


def classifier_from_settings(settings: Settings) -> ImageClassifier | None:
    return FakeImageClassifier() if settings.image_classifier == "fake" else None
