"""The avatar (P2-T02c1, end of gap E13 of P1): one of the member's own photos, sent as an
avatar and processed; shown on /v1/me and the public profile; the one it replaces is deleted."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_profile import T0, Account, make_account
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]
_VARIANTS = (
    '[{"format": "avif", "width": 320, "height": 320, "key": "K1", "bytes": 10},'
    ' {"format": "webp", "width": 640, "height": 640, "key": "K2", "bytes": 20}]'
)


@pytest.fixture
async def client(sessionmaker: Session, redis_client: Redis) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings(media_public_url="https://media.example/"))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = FixedClock(T0)
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


async def _photo(
    sessionmaker: Session, owner: UUID, *, purpose: str = "avatar", status: str = "ready"
) -> UUID:
    media_id, key = new_id(), new_id().hex
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
                " status, sha256, exif_stripped, variants, rejection_reason)"
                " VALUES (:id, :owner, 'image', :purpose, :key, 'image/jpeg', 1000, :status,"
                " CASE WHEN :status = 'ready' THEN CAST(:sha AS bytea) END, :status = 'ready',"
                " CASE WHEN :status = 'ready' THEN CAST(:variants AS jsonb) ELSE '[]' END,"
                " CASE WHEN :status = 'rejected' THEN 'type_mismatch' END)"
            ),
            {
                "id": media_id,
                "owner": owner,
                "purpose": purpose,
                "key": key,
                "status": status,
                "sha": b"\x01" * 32,
                "variants": _VARIANTS.replace("K1", new_id().hex).replace("K2", new_id().hex),
            },
        )
        await db.commit()
    return media_id


async def _me(client: AsyncClient, account: Account) -> dict[str, Any]:
    return (await client.get("/v1/me", headers=account.headers)).json()


async def _set_avatar(client: AsyncClient, account: Account, media_id: UUID | None) -> Any:
    version = (await _me(client, account))["version"]
    headers = account.headers | {"if-match": str(version)}
    body = {"avatar_media_id": None if media_id is None else str(media_id)}
    return await client.patch("/v1/me", headers=headers, json=body)


async def _deleted(sessionmaker: Session, media_id: UUID) -> bool:
    async with sessionmaker() as db:
        return bool(
            await db.scalar(
                text("SELECT deleted_at IS NOT NULL FROM media WHERE id = :id"), {"id": media_id}
            )
        )


async def test_avatar_must_be_own_ready_avatar_media(
    sessionmaker: Session, client: AsyncClient
) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    cases = [
        (await _photo(sessionmaker, other.id), 404, "not_found"),
        (new_id(), 404, "not_found"),
        (await _photo(sessionmaker, member.id, status="processing"), 409, "media_not_ready"),
        (await _photo(sessionmaker, member.id, purpose="listing"), 422, "media_not_avatar"),
        (await _photo(sessionmaker, member.id, status="rejected"), 422, "media_rejected"),
    ]
    for media_id, status, code in cases:
        response = await _set_avatar(client, member, media_id)
        assert (response.status_code, response.json()["code"]) == (status, code), media_id
    me = await _me(client, member)
    assert (me["avatar"], me["avatar_media_id"]) == (None, None)


async def test_avatar_not_shown_unless_ready(sessionmaker: Session, client: AsyncClient) -> None:
    member = await make_account(sessionmaker, completed=True)
    media_id = await _photo(sessionmaker, member.id)
    assert (await _set_avatar(client, member, media_id)).status_code == 200
    async with sessionmaker() as db:  # cannot happen today: a ready photo stays ready
        await db.execute(
            text("UPDATE media SET status = 'processing', sha256 = NULL WHERE id = :id"),
            {"id": media_id},
        )
        await db.commit()
    assert (await _me(client, member))["avatar"] is None


async def test_avatar_in_me_and_public_profile(sessionmaker: Session, client: AsyncClient) -> None:
    member = await make_account(sessionmaker, completed=True)
    media_id = await _photo(sessionmaker, member.id)
    response = await _set_avatar(client, member, media_id)
    assert response.status_code == 200, response.text
    me = response.json()
    assert me["avatar_media_id"] == str(media_id)
    assert [(v["format"], v["width"], v["height"]) for v in me["avatar"]] == [
        ("avif", 320, 320),
        ("webp", 640, 640),
    ]
    assert all(v["url"].startswith("https://media.example/") for v in me["avatar"])
    assert "//" not in me["avatar"][0]["url"].removeprefix("https://")
    public = (await client.get(f"/v1/users/{me['username']}")).json()
    assert public["avatar"] == me["avatar"]
    assert "avatar_media_id" not in public


async def test_replacing_avatar_deletes_old(sessionmaker: Session, client: AsyncClient) -> None:
    member = await make_account(sessionmaker, completed=True)
    first, second = await _photo(sessionmaker, member.id), await _photo(sessionmaker, member.id)
    assert (await _set_avatar(client, member, first)).status_code == 200
    assert (await _set_avatar(client, member, first)).status_code == 200  # same: kept
    assert not await _deleted(sessionmaker, first)
    assert (await _set_avatar(client, member, second)).status_code == 200
    assert await _deleted(sessionmaker, first) and not await _deleted(sessionmaker, second)
    removed = await _set_avatar(client, member, None)
    assert (removed.json()["avatar"], removed.json()["avatar_media_id"]) == (None, None)
    assert await _deleted(sessionmaker, second)
    # A deleted photo cannot come back as the avatar.
    assert (await _set_avatar(client, member, first)).status_code == 404


async def test_avatar_not_shown_once_its_media_is_gone(
    sessionmaker: Session, client: AsyncClient
) -> None:
    member = await make_account(sessionmaker, completed=True)
    media_id = await _photo(sessionmaker, member.id)
    assert (await _set_avatar(client, member, media_id)).status_code == 200
    async with sessionmaker() as db:  # withdrawn by moderation, for instance
        await db.execute(
            text("UPDATE media SET deleted_at = now() WHERE id = :id"), {"id": media_id}
        )
        await db.commit()
    assert (await _me(client, member))["avatar"] is None
