"""Text embeddings of listings behind a protocol (P2-T11, ADR-0020, plan Q9, E5): a model of
`DIMENSION` numbers in an EU region, its name kept with each vector. None configured: listings
have no embedding (no similar listings yet); the fake one, deterministic, is for tests and
local development. The adapter on AWS Bedrock comes when Arcel opens the access (Q18)."""

import hashlib
import math
import re
import unicodedata
from typing import Protocol

from trovelya.core.config import Settings

DIMENSION = 1024  # `listings.embedding VECTOR(1024)`


class Embedder(Protocol):
    model: str  # stored in `listings.embedding_model`: a new model means reindexing

    async def embed(self, text: str) -> list[float]:
        """`DIMENSION` finite numbers; raises when the provider fails."""
        ...


FLOAT32_MAX = 3.4e38


def checked_vector(vector: list[float]) -> list[float]:
    """The vector as a model must give it, or ValueError (never a wrong one stored): `DIMENSION`
    numbers within float32, not all zero (a zero vector has no cosine distance)."""
    try:
        numbers = [float(x) for x in vector if not isinstance(x, bool)]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"an embedding has {DIMENSION} numbers") from exc
    if len(numbers) != len(vector) or len(numbers) != DIMENSION:
        raise ValueError(f"an embedding has {DIMENSION} finite numbers")
    if not all(math.isfinite(x) and abs(x) < FLOAT32_MAX for x in numbers):
        raise ValueError(f"an embedding has {DIMENSION} finite numbers")
    if math.sqrt(sum(x * x for x in numbers)) < 1e-6:
        raise ValueError(f"an embedding of {DIMENSION} zeros has no direction")
    return numbers


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.findall(r"\w+", plain)


class FakeEmbedder:
    """Hashed bag of words, normalised: texts sharing words are close, deterministically."""

    def __init__(self, model: str = "fake-words-v1") -> None:
        self.model = model

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSION
        for word in _words(text):
            digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % DIMENSION
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


def embedder_from_settings(settings: Settings) -> Embedder | None:
    return FakeEmbedder() if settings.embedder == "fake" else None


def current_model(settings: Settings) -> str | None:
    """The model whose vectors are compared (ADR-0020); None without an embedder."""
    embedder = embedder_from_settings(settings)
    return None if embedder is None else embedder.model
