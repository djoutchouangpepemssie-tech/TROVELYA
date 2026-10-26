"""Storage keys and the in-memory storage used by unit tests (ADR-0019)."""

import re

import pytest
from pydantic import ValidationError

from tests.conftest import make_settings
from trovelya.modules.media.adapters.storage import (
    MemoryStorage,
    S3Storage,
    new_storage_key,
    storage_from_settings,
)

S3 = {
    "storage_endpoint": "https://account.eu.r2.cloudflarestorage.com",
    "storage_access_key_id": "id",
    "storage_secret_access_key": "secret",
}


def test_storage_key_is_random_128_bits() -> None:
    keys = {new_storage_key() for _ in range(1000)}
    assert len(keys) == 1000
    assert all(re.fullmatch(r"[0-9a-f]{32}", key) for key in keys)


async def test_memory_storage_round_trip() -> None:
    storage = MemoryStorage()
    upload = storage.presign_put(
        "originals", "k", content_type="image/png", content_length=3, expires_in=300
    )
    assert upload.headers == {"Content-Type": "image/png"} and upload.expires_in == 300
    assert await storage.size("originals", "k") is None
    await storage.put("originals", "k", b"png", content_type="image/png")
    assert (await storage.size("originals", "k"), await storage.get("originals", "k")) == (
        3,
        b"png",
    )
    await storage.delete("originals", "k")
    await storage.delete("originals", "k")
    assert await storage.size("originals", "k") is None


def test_s3_storage_needs_endpoint_and_keys() -> None:
    with pytest.raises(ValidationError, match="STORAGE_ENDPOINT"):
        make_settings(storage_provider="s3", storage_endpoint="https://r2.example")


def test_empty_storage_keys_are_missing_keys() -> None:
    with pytest.raises(ValidationError, match="STORAGE_ENDPOINT"):
        make_settings(
            storage_provider="s3",
            storage_endpoint="https://r2.example",
            storage_access_key_id="",
            storage_secret_access_key="",
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"storage_provider": "s3", **S3, "media_public_url": "http://media.example"},
        {"storage_provider": "s3", **S3},
    ],
    ids=["memory", "http", "no-public-url"],
)
def test_production_stores_media_for_real(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="production needs"):
        make_settings(env="production", **overrides)
    make_settings(env="production", storage_provider="s3", **S3, media_public_url="https://m.fr")


def test_upload_url_lives_five_minutes_at_most() -> None:
    storage = storage_from_settings(make_settings(storage_provider="s3", **S3))
    for expires_in in (0, 301):
        with pytest.raises(ValueError, match="upload URL"):
            storage.presign_put(
                "originals",
                "0" * 32,
                content_type="image/jpeg",
                content_length=1,
                expires_in=expires_in,
            )


def test_storage_from_settings() -> None:
    assert isinstance(storage_from_settings(make_settings()), MemoryStorage)
    storage = storage_from_settings(
        make_settings(
            storage_provider="s3",
            storage_endpoint="https://account.eu.r2.cloudflarestorage.com",
            storage_access_key_id="id",
            storage_secret_access_key="secret",
        )
    )
    assert isinstance(storage, S3Storage)
    upload = storage.presign_put(
        "originals", "0" * 32, content_type="image/jpeg", content_length=10, expires_in=300
    )
    assert upload.url.startswith(
        "https://account.eu.r2.cloudflarestorage.com/trovelya-originals/" + "0" * 32 + "?"
    )
    assert "X-Amz-Expires=300" in upload.url
    assert "X-Amz-SignedHeaders=content-length%3Bcontent-type%3Bhost" in upload.url
