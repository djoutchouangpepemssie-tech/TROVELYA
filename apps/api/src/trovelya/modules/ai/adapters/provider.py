"""AI providers (P2-T06a, ADR-0021 to come): what a model says about an item's photos.

The provider sees the photos (their 1080 px variant) and the active leaves of the catalogue,
and answers a JSON object; its cost is announced in micro-euros. It is never trusted: the
server checks the answer against the schema, then against the catalogue. `FakeAIProvider`
answers the same suggestion whatever the photos, for development and tests only."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from trovelya.core.config import Settings


@dataclass(frozen=True, slots=True)
class ImageRef:
    """A photo as the provider reads it: a variant in the variants bucket."""

    key: str
    format: str
    width: int


@dataclass(frozen=True, slots=True)
class Leaf:
    """A category an item may be listed in: its key and its French name."""

    key: str
    name: str


@dataclass(frozen=True, slots=True)
class ProviderAnswer:
    output: Any  # the JSON the model gave, not yet checked
    cost_microeur: int


class AIProvider(Protocol):
    model: str

    async def suggest_listing(
        self, images: Sequence[ImageRef], leaves: Sequence[Leaf]
    ) -> ProviderAnswer: ...


class FakeAIProvider:
    """The same linen dress for any photo; half a cent per call."""

    def __init__(self, model: str = "fake-assist-v1") -> None:
        self.model = model

    async def suggest_listing(
        self, images: Sequence[ImageRef], leaves: Sequence[Leaf]
    ) -> ProviderAnswer:
        output = {
            "title": "Robe en lin bleue",
            "category_key": "mode.femme.robes",
            "brand": None,
            "condition": "very_good",
            "attributes": {"clothing_size": "m", "color": "bleu"},
            "caption": "Robe bleue en lin posée à plat",
            "confidence": {"title": 0.9, "category": 0.8, "condition": 0.6, "attributes": 0.7},
        }
        return ProviderAnswer(output=output, cost_microeur=500)


def ai_provider_from_settings(settings: Settings) -> AIProvider | None:
    return FakeAIProvider() if settings.ai_provider == "fake" else None
