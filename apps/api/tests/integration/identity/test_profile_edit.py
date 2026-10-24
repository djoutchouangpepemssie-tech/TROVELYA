"""Editing the profile with optimistic locking, and the public profile (P1-T05b, 11.1)."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import Account, client, make_account
from trovelya.shared.ids import new_id

__all__ = ["client"]  # the fixture, shared with test_profile


async def _me(client: AsyncClient, account: Account) -> dict[str, Any]:
    return (await client.get("/v1/me", headers=account.headers)).json()


async def _patch(
    client: AsyncClient, account: Account, body: dict[str, Any], version: int | None
) -> Any:
    headers = dict(account.headers)
    if version is not None:
        headers["if-match"] = str(version)
    return await client.patch("/v1/me", headers=headers, json=body)


async def test_patch_requires_if_match(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker, completed=True)
    version = (await _me(client, account))["version"]
    missing = await _patch(client, account, {"display_name": "A"}, None)
    assert missing.status_code == 428 and missing.json()["code"] == "precondition_required"
    stale = await _patch(client, account, {"display_name": "A"}, version - 1)
    assert stale.status_code == 412 and stale.json()["code"] == "precondition_failed"
    ok = await _patch(client, account, {"display_name": "Arcel"}, version)
    assert ok.status_code == 200, ok.text
    assert ok.json()["display_name"] == "Arcel" and ok.json()["version"] == version + 1
    # The same version cannot be used twice: the second writer is told to reload.
    assert (await _patch(client, account, {"display_name": "B"}, version)).status_code == 412


async def test_patch_fields(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker, completed=True)
    me = await _me(client, account)
    new_username = f"New_{new_id().hex[-8:]}"
    response = await _patch(
        client,
        account,
        {"username": new_username, "bio": "Collectionneur de montres.", "locale": "fr-FR"},
        me["version"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == new_username.lower() and body["bio"] == "Collectionneur de montres."
    cleared = await _patch(client, account, {"bio": "  "}, body["version"])
    assert cleared.json()["bio"] is None


async def test_patch_rejects_invalid_values(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker, completed=True)
    version = (await _me(client, account))["version"]
    for body in (
        {"locale": "en-US"},
        {"username": "a!"},
        {"display_name": ""},
        {"bio": "x" * 501},
        {"email": "other@example.org"},
        {"username": None},
        {"display_name": None},
    ):
        assert (await _patch(client, account, body, version)).status_code == 422, body


async def test_patch_username_taken(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    taken = f"taken_{new_id().hex[-8:]}"
    await make_account(sessionmaker, username=taken, completed=True)
    account = await make_account(sessionmaker, completed=True)
    version = (await _me(client, account))["version"]
    response = await _patch(client, account, {"username": taken.upper()}, version)
    assert response.status_code == 409 and response.json()["code"] == "username_taken"


async def test_patch_needs_completed_profile(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    account = await make_account(sessionmaker)
    version = (await _me(client, account))["version"]
    response = await _patch(client, account, {"display_name": "X"}, version)
    assert response.status_code == 403


# --- Public profile ------------------------------------------------------------------------


async def test_public_profile_has_no_email_or_location(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    username = f"public_{new_id().hex[-8:]}"
    account = await make_account(sessionmaker, username=username, completed=True)
    follower = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        await db.execute(
            text("INSERT INTO follows (follower_id, followee_user_id) VALUES (:a, :b)"),
            {"a": follower.id, "b": account.id},
        )
        await db.commit()
    response = await client.get(f"/v1/users/{username.upper()}")
    assert response.status_code == 200
    profile = response.json()
    assert set(profile) == {
        "id",
        "username",
        "display_name",
        "bio",
        "member_since",
        "followers_count",
        "following_count",
        "viewer",
    }
    assert profile["viewer"] is None  # nobody signed in
    assert profile["username"] == username
    assert (profile["followers_count"], profile["following_count"]) == (1, 0)
    assert account.email not in response.text


async def _set(sessionmaker: async_sessionmaker[AsyncSession], sql: str, user_id: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(text(sql), {"id": user_id})
        await db.commit()


async def test_public_profile_404_when_erasure_requested(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    username = f"erased_{new_id().hex[-8:]}"
    account = await make_account(sessionmaker, username=username, completed=True)
    await _set(
        sessionmaker, "UPDATE users SET erasure_requested_at = now() WHERE id = :id", account.id
    )
    assert (await client.get(f"/v1/users/{username}")).status_code == 404


async def test_public_profile_visibility_by_status(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    username = f"status_{new_id().hex[-8:]}"
    account = await make_account(sessionmaker, username=username, completed=True)
    path = f"/v1/users/{username}"
    await _set(sessionmaker, "UPDATE users SET status = 'restricted' WHERE id = :id", account.id)
    assert (await client.get(path)).status_code == 200
    await _set(sessionmaker, "UPDATE users SET status = 'suspended' WHERE id = :id", account.id)
    assert (await client.get(path)).status_code == 404
    # Not completed yet (provisional username), unknown, or an invalid name.
    incomplete = await make_account(sessionmaker)
    me = (await client.get("/v1/me", headers=incomplete.headers)).json()
    assert (await client.get(f"/v1/users/{me['username']}")).status_code == 404
    assert (await client.get("/v1/users/nobody_here_123")).status_code == 404
    assert (await client.get("/v1/users/x!")).status_code == 404
