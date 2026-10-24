"""Following and blocking members (P1-T10, Q14)."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import Account, client, make_account
from trovelya.shared.ids import new_id

__all__ = ["client"]


async def _member(sessionmaker: async_sessionmaker[AsyncSession]) -> Account:
    return await make_account(sessionmaker, username=f"m_{new_id().hex[-10:]}", completed=True)


async def _username(sessionmaker: async_sessionmaker[AsyncSession], account: Account) -> str:
    async with sessionmaker() as db:
        return str(
            await db.scalar(
                text("SELECT username::text FROM users WHERE id = :id"), {"id": account.id}
            )
        )


async def _profile(
    client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    account: Account,
    viewer: Account | None = None,
) -> dict[str, Any]:
    headers = viewer.headers if viewer else {}
    response = await client.get(
        f"/v1/users/{await _username(sessionmaker, account)}", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_follow_unfollow_idempotent(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    me, them = await _member(sessionmaker), await _member(sessionmaker)
    path = f"/v1/users/{them.id}/follow"
    for _ in range(2):
        assert (await client.post(path, headers=me.headers)).status_code == 204
    profile = await _profile(client, sessionmaker, them, viewer=me)
    assert profile["id"] == str(them.id)
    assert profile["followers_count"] == 1
    assert profile["viewer"] == {"following": True, "blocking": False}
    for _ in range(2):
        assert (await client.delete(path, headers=me.headers)).status_code == 204
    profile = await _profile(client, sessionmaker, them, viewer=me)
    assert profile["followers_count"] == 0 and profile["viewer"]["following"] is False


async def test_anonymous_viewer_has_no_relationship(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    them = await _member(sessionmaker)
    assert (await _profile(client, sessionmaker, them))["viewer"] is None


async def test_cannot_follow_or_block_self(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    me = await _member(sessionmaker)
    for action in ("follow", "block"):
        response = await client.post(f"/v1/users/{me.id}/{action}", headers=me.headers)
        assert response.status_code == 422, action


async def test_block_removes_follows_both_ways(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    me, them = await _member(sessionmaker), await _member(sessionmaker)
    await client.post(f"/v1/users/{them.id}/follow", headers=me.headers)
    await client.post(f"/v1/users/{me.id}/follow", headers=them.headers)
    for _ in range(2):
        assert (
            await client.post(f"/v1/users/{them.id}/block", headers=me.headers)
        ).status_code == 204
    mine = await _profile(client, sessionmaker, me)
    theirs = await _profile(client, sessionmaker, them, viewer=me)
    assert (mine["followers_count"], mine["following_count"]) == (0, 0)
    assert (theirs["followers_count"], theirs["following_count"]) == (0, 0)
    assert theirs["viewer"] == {"following": False, "blocking": True}
    blocks = (await client.get("/v1/me/blocks", headers=me.headers)).json()["data"]
    assert [b["user_id"] for b in blocks] == [str(them.id)]
    assert blocks[0]["username"] == await _username(sessionmaker, them)

    # Unblocking does not bring the follows back.
    for _ in range(2):
        assert (
            await client.delete(f"/v1/users/{them.id}/block", headers=me.headers)
        ).status_code == 204
    assert (await client.get("/v1/me/blocks", headers=me.headers)).json()["data"] == []
    assert (await _profile(client, sessionmaker, them))["followers_count"] == 0


async def test_follow_blocked_returns_404(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    """Either way: the person who is blocked must not learn it (Q14)."""
    me, them = await _member(sessionmaker), await _member(sessionmaker)
    await client.post(f"/v1/users/{me.id}/block", headers=them.headers)
    blocked_response = await client.post(f"/v1/users/{them.id}/follow", headers=me.headers)
    unknown_response = await client.post(f"/v1/users/{new_id()}/follow", headers=me.headers)
    assert blocked_response.status_code == unknown_response.status_code == 404
    assert blocked_response.json()["code"] == unknown_response.json()["code"]
    # The one who blocked cannot follow either.
    assert (await client.post(f"/v1/users/{me.id}/follow", headers=them.headers)).status_code == 404
    # The public profile stays visible, and does not say "blocked" to the blocked person.
    assert (await _profile(client, sessionmaker, them, viewer=me))["viewer"] == {
        "following": False,
        "blocking": False,
    }


async def test_unknown_user_404(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    me = await _member(sessionmaker)
    incomplete = await make_account(sessionmaker)
    hidden = await _member(sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE users SET erasure_requested_at = now() WHERE id = :id"), {"id": hidden.id}
        )
        await db.commit()
    for target in (new_id(), incomplete.id, hidden.id):
        for action in ("follow", "block"):
            response = await client.post(f"/v1/users/{target}/{action}", headers=me.headers)
            assert response.status_code == 404, (target, action)
    assert (await client.post("/v1/users/pas-un-id/follow", headers=me.headers)).status_code == 422


async def test_counters(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    star = await _member(sessionmaker)
    fans = [await _member(sessionmaker) for _ in range(3)]
    for fan in fans:
        await client.post(f"/v1/users/{star.id}/follow", headers=fan.headers)
    await client.post(f"/v1/users/{fans[0].id}/follow", headers=star.headers)
    profile = await _profile(client, sessionmaker, star)
    assert (profile["followers_count"], profile["following_count"]) == (3, 1)


async def test_social_needs_a_signed_in_completed_profile(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    them = await _member(sessionmaker)
    incomplete = await make_account(sessionmaker)
    assert (await client.post(f"/v1/users/{them.id}/follow")).status_code == 401
    response = await client.post(f"/v1/users/{them.id}/follow", headers=incomplete.headers)
    assert response.status_code == 403 and response.json()["code"] == "profile_incomplete"
    assert (await client.get("/v1/me/blocks")).status_code == 401
