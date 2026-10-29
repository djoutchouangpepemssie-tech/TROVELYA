"""Image classification behind a protocol (P2-T05b2, section 8.17, plan Q38, Q39): scores from
0 to 1 for nudity, violence, weapons and drugs, by an EU provider chosen before production. The
classifier gets the re-encoded image only: never the seller's text, never metadata.

Until a provider is configured there is no classifier: listing photos stay unclassified and
the listing goes to human review (Q38). The fake one exists for tests and local development.
"""

from collections.abc import Mapping
from typing import Protocol

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


def classifier_from_settings(settings: Settings) -> ImageClassifier | None:
    return FakeImageClassifier() if settings.image_classifier == "fake" else None
