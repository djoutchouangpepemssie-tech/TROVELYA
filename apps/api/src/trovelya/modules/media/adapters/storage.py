"""Object storage behind a protocol (ADR-0019): Cloudflare R2 on Railway, Garage locally and
in tests (both speak S3), an in-memory fake for unit tests.

Two buckets: `originals` (private; what the browser uploads, deleted once processed) and
`variants` (public; re-encoded images only). Keys are random and carry no personal data.
"""

import asyncio
import secrets
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast

# boto3 ships no type stubs; the client is typed Any and wrapped by this module only.
import boto3  # pyright: ignore[reportMissingTypeStubs]
from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]
from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]

from trovelya.core.config import Settings

Bucket = Literal["originals", "variants"]
KEY_BYTES = 16  # 128 bits: a key can be neither guessed nor enumerated (capability URL)
MAX_UPLOAD_SECONDS = 300  # an upload URL lives 5 minutes at most (ADR-0019)
# Variants never change: a new image gets a new key.
IMMUTABLE = "public, max-age=31536000, immutable"


def new_storage_key() -> str:
    """32 lowercase hex characters, random; never derived from a name, an id or a member."""
    return secrets.token_hex(KEY_BYTES)


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    headers: dict[str, str]  # to send exactly as given: they are part of the signature
    expires_in: int


class ObjectStorage(Protocol):
    def presign_put(
        self, bucket: Bucket, key: str, *, content_type: str, content_length: int, expires_in: int
    ) -> PresignedUpload:
        """A one-object PUT URL whose type and length are signed: any other is refused."""
        ...

    async def size(self, bucket: Bucket, key: str) -> int | None:
        """The stored object's real size, or None when nothing was uploaded."""
        ...

    async def get(self, bucket: Bucket, key: str, *, max_bytes: int | None = None) -> bytes:
        """The object's bytes; with `max_bytes`, at most max_bytes + 1 of them (enough to tell
        that it is too large without reading it all)."""
        ...

    async def put(self, bucket: Bucket, key: str, data: bytes, *, content_type: str) -> None: ...

    async def delete(self, bucket: Bucket, key: str) -> None:
        """Idempotent: deleting a missing object is not an error."""
        ...


class S3Storage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        buckets: dict[Bucket, str],
    ) -> None:
        self._buckets = buckets
        self._client: Any = boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
                # As many connections as threads asyncio.to_thread may run at once.
                max_pool_connections=32,
            ),
        )

    def presign_put(
        self, bucket: Bucket, key: str, *, content_type: str, content_length: int, expires_in: int
    ) -> PresignedUpload:
        if not 0 < expires_in <= MAX_UPLOAD_SECONDS:
            raise ValueError(f"an upload URL lives 1 to {MAX_UPLOAD_SECONDS} seconds")
        url: str = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._buckets[bucket],
                "Key": key,
                "ContentType": content_type,
                "ContentLength": content_length,
            },
            ExpiresIn=expires_in,
        )
        return PresignedUpload(
            url=url, headers={"Content-Type": content_type}, expires_in=expires_in
        )

    async def size(self, bucket: Bucket, key: str) -> int | None:
        # A token without ListBucket gets 403, not 404, for a missing object: R2 tokens
        # scoped to the buckets (infra/r2/README.md) include it.
        try:
            head = await asyncio.to_thread(
                self._client.head_object, Bucket=self._buckets[bucket], Key=key
            )
        except ClientError as exc:
            response = cast(dict[str, dict[str, str]], exc.response)  # pyright: ignore[reportUnknownMemberType]
            if response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return int(head["ContentLength"])

    async def get(self, bucket: Bucket, key: str, *, max_bytes: int | None = None) -> bytes:
        extra = {} if max_bytes is None else {"Range": f"bytes=0-{max_bytes}"}
        response = await asyncio.to_thread(
            self._client.get_object, Bucket=self._buckets[bucket], Key=key, **extra
        )
        return await asyncio.to_thread(response["Body"].read)

    async def put(self, bucket: Bucket, key: str, data: bytes, *, content_type: str) -> None:
        extra = {"CacheControl": IMMUTABLE} if bucket == "variants" else {}
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._buckets[bucket],
            Key=key,
            Body=data,
            ContentType=content_type,
            **extra,
        )

    async def delete(self, bucket: Bucket, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._buckets[bucket], Key=key)


@dataclass
class MemoryStorage:
    """Unit tests: objects in a dict; presigned URLs are opaque and never fetched."""

    objects: dict[tuple[Bucket, str], tuple[bytes, str]] = field(
        default_factory=dict[tuple[Bucket, str], tuple[bytes, str]]
    )

    def presign_put(
        self, bucket: Bucket, key: str, *, content_type: str, content_length: int, expires_in: int
    ) -> PresignedUpload:
        return PresignedUpload(
            url=f"memory://{bucket}/{key}?length={content_length}&expires={expires_in}",
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    async def size(self, bucket: Bucket, key: str) -> int | None:
        stored = self.objects.get((bucket, key))
        return None if stored is None else len(stored[0])

    async def get(self, bucket: Bucket, key: str, *, max_bytes: int | None = None) -> bytes:
        data = self.objects[(bucket, key)][0]
        return data if max_bytes is None else data[: max_bytes + 1]

    async def put(self, bucket: Bucket, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[(bucket, key)] = (data, content_type)

    async def delete(self, bucket: Bucket, key: str) -> None:
        self.objects.pop((bucket, key), None)


def storage_from_settings(settings: Settings) -> ObjectStorage:
    if settings.storage_provider == "memory":
        return MemoryStorage()
    endpoint = settings.storage_endpoint
    key_id, secret = settings.storage_access_key_id, settings.storage_secret_access_key
    if endpoint is None or key_id is None or secret is None:  # refused by Settings already
        raise ValueError("incomplete S3 storage settings")
    return S3Storage(
        endpoint_url=endpoint,
        region=settings.storage_region,
        access_key_id=key_id.get_secret_value(),
        secret_access_key=secret.get_secret_value(),
        buckets={
            "originals": settings.storage_bucket_originals,
            "variants": settings.storage_bucket_variants,
        },
    )
