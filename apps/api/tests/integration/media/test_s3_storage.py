"""Uploads straight to object storage (P2-T02a2, ADR-0019), checked against a real S3 server:
the presigned URL signs the type and the length, so the storage itself refuses anything
else (13.2)."""

import asyncio

import httpx
import pytest
from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]

from tests.integration.media.conftest import BUCKETS
from trovelya.modules.media.adapters.storage import IMMUTABLE, S3Storage, new_storage_key

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 996


async def _put(url: str, data: bytes, content_type: str) -> int:
    async with httpx.AsyncClient() as client:
        response = await client.put(url, content=data, headers={"Content-Type": content_type})
        return response.status_code


async def test_presigned_put_accepts_the_declared_file(garage: S3Storage) -> None:
    key = new_storage_key()
    upload = garage.presign_put(
        "originals", key, content_type="image/jpeg", content_length=len(JPEG), expires_in=300
    )
    assert await _put(upload.url, JPEG, upload.headers["Content-Type"]) == 200
    assert await garage.size("originals", key) == len(JPEG)
    assert await garage.get("originals", key) == JPEG


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (JPEG + b"more", "image/jpeg"),  # longer than declared
        (JPEG[:-1], "image/jpeg"),  # shorter
        (JPEG, "text/html"),  # another type
        (JPEG, "image/svg+xml"),
    ],
    ids=["longer", "shorter", "html", "svg"],
)
async def test_presigned_put_refuses_anything_else(
    garage: S3Storage, data: bytes, content_type: str
) -> None:
    key = new_storage_key()
    upload = garage.presign_put(
        "originals", key, content_type="image/jpeg", content_length=len(JPEG), expires_in=300
    )
    assert await _put(upload.url, data, content_type) == 403
    assert await garage.size("originals", key) is None


async def test_presigned_put_expires(garage: S3Storage) -> None:
    key = new_storage_key()
    upload = garage.presign_put(
        "originals", key, content_type="image/jpeg", content_length=len(JPEG), expires_in=1
    )
    await asyncio.sleep(2.5)
    assert await _put(upload.url, JPEG, "image/jpeg") in {400, 403}  # refused, either way
    assert await garage.size("originals", key) is None


async def test_presigned_url_names_one_object(garage: S3Storage) -> None:
    upload = garage.presign_put(
        "originals",
        new_storage_key(),
        content_type="image/jpeg",
        content_length=len(JPEG),
        expires_in=300,
    )
    other = upload.url.replace(upload.url.split("?")[0].rsplit("/", 1)[1], new_storage_key())
    assert await _put(other, JPEG, "image/jpeg") == 403


async def test_put_size_and_delete(garage: S3Storage) -> None:
    key = new_storage_key()
    await garage.put("variants", key, b"webp", content_type="image/webp")
    assert await garage.size("variants", key) == 4
    head = garage._client.head_object(Bucket=BUCKETS["variants"], Key=key)  # pyright: ignore[reportPrivateUsage]
    assert (head["ContentType"], head["CacheControl"]) == ("image/webp", IMMUTABLE)
    await garage.delete("variants", key)
    await garage.delete("variants", key)  # idempotent
    assert await garage.size("variants", key) is None


async def test_originals_are_not_cached_publicly(garage: S3Storage) -> None:
    key = new_storage_key()
    await garage.put("originals", key, JPEG, content_type="image/jpeg")
    head = garage._client.head_object(Bucket=BUCKETS["originals"], Key=key)  # pyright: ignore[reportPrivateUsage]
    assert "CacheControl" not in head


async def test_storage_errors_are_not_taken_for_a_missing_file(garage: S3Storage) -> None:
    """Only « not found » means nothing was uploaded; a refused request is an error."""
    endpoint: str = garage._client.meta.endpoint_url  # pyright: ignore[reportPrivateUsage]
    wrong = S3Storage(
        endpoint_url=endpoint,
        region="garage",
        access_key_id="GK00000000000000000000000",
        secret_access_key="0" * 64,
        buckets=BUCKETS,
    )
    with pytest.raises(ClientError):
        await wrong.size("originals", new_storage_key())


async def test_bounded_read(garage: S3Storage) -> None:
    """At most max_bytes + 1 bytes come back: enough to see a file is too large."""
    key = new_storage_key()
    await garage.put("originals", key, b"x" * 100, content_type="image/png")
    assert len(await garage.get("originals", key, max_bytes=10)) == 11
    assert len(await garage.get("originals", key, max_bytes=500)) == 100
