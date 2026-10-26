"""The media table (P2-T02a1, section 7.5 with gap E11 of the P2 plan): every constraint has a
case below."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trovelya.shared.ids import new_id

_INSERT_MEDIA = text(
    "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes, status,"
    " sha256, exif_stripped, variants, rejection_reason, width)"
    " VALUES (:id, :owner_id, :kind, :purpose, :storage_key, :mime_type, :bytes, :status,"
    " :sha256, :exif_stripped, CAST(:variants AS jsonb), :rejection_reason, :width)"
)
_HASH = b"\x01" * 32
_VARIANTS = '[{"format":"webp","width":320,"height":240,"key":"' + "a" * 32 + '","bytes":10}]'


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


@pytest.fixture
async def owner(conn: AsyncConnection) -> Any:
    user_id = new_id()
    await conn.execute(
        text(
            "INSERT INTO users (id, email, username, display_name)"
            " VALUES (:id, :email, :username, 'Membre')"
        ),
        {"id": user_id, "email": f"{user_id.hex}@example.org", "username": f"u_{user_id.hex[-8:]}"},
    )
    return user_id


def _media(owner: Any, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_id(),
        "owner_id": owner,
        "kind": "image",
        "purpose": "listing",
        "storage_key": new_id().hex,
        "mime_type": "image/jpeg",
        "bytes": 1000,
        "status": "uploading",
        "sha256": None,
        "exif_stripped": False,
        "variants": "[]",
        "rejection_reason": None,
        "width": None,
    } | overrides


async def _fails(conn: AsyncConnection, params: dict[str, Any]) -> str:
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(_INSERT_MEDIA, params)
    await savepoint.rollback()
    return str(error.value)


async def test_an_upload_starts_without_hash(conn: AsyncConnection, owner: Any) -> None:
    await conn.execute(_INSERT_MEDIA, _media(owner))


async def test_a_ready_image_is_complete(conn: AsyncConnection, owner: Any) -> None:
    ready = {
        "status": "ready",
        "sha256": b"\x01" * 32,
        "exif_stripped": True,
        "variants": _VARIANTS,
    }
    await conn.execute(_INSERT_MEDIA, _media(owner, **ready))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"kind": "gif"}, "media_kind_check"),
        ({"purpose": "banner"}, "media_purpose_check"),
        ({"status": "deleted"}, "media_status_check"),
        ({"storage_key": "photo-de-jean.jpg"}, "media_storage_key_check"),
        ({"storage_key": "A" * 32}, "media_storage_key_check"),
        ({"bytes": 0}, "media_bytes_check"),
        ({"width": 0}, "media_width_check"),
        ({"sha256": b"\x01" * 31}, "media_sha256_check"),
        ({"variants": "{}"}, "media_variants_check"),
        ({"status": "ready"}, "media_ready_is_complete"),
        (
            {
                "status": "ready",
                "sha256": b"\x01" * 32,
                "exif_stripped": False,
                "variants": _VARIANTS,
            },
            "media_ready_is_complete",
        ),
        (
            {"status": "ready", "sha256": b"\x01" * 32, "exif_stripped": True},
            "media_ready_is_complete",
        ),
        ({"status": "rejected"}, "media_rejected_has_reason"),
        ({"rejection_reason": "type"}, "media_rejected_has_reason"),
        ({"owner_id": new_id()}, "media_owner_id_fkey"),
    ],
)
async def test_media_checks(
    conn: AsyncConnection, owner: Any, overrides: dict[str, Any], constraint: str
) -> None:
    assert constraint in await _fails(conn, _media(owner, **overrides))


async def test_storage_key_unique(conn: AsyncConnection, owner: Any) -> None:
    media = _media(owner)
    await conn.execute(_INSERT_MEDIA, media)
    assert "media_storage_key_key" in await _fails(
        conn, _media(owner, storage_key=media["storage_key"])
    )


async def test_avatar_refers_to_a_media(conn: AsyncConnection, owner: Any) -> None:
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError, match="users_avatar_media_id_fkey"):
        await conn.execute(
            text("UPDATE users SET avatar_media_id = :m WHERE id = :u"), {"m": new_id(), "u": owner}
        )
    await savepoint.rollback()
