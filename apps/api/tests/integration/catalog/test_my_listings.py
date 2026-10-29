"""`GET /v1/me/listings`: the seller's own listings (P2-T03b3b, section 11.3 and 11.5), newest
first, any status (deleted ones left out), cursor pagination `{data, next_cursor, has_more}`."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_draft_rules import photo
from tests.integration.catalog.test_drafts import Session, create, draft, seller
from tests.integration.identity.test_profile import Account, make_account


async def _mine(client: AsyncClient, account: Account, **params: Any) -> Any:
    return await client.get("/v1/me/listings", headers=account.headers, params=params)


async def _drafts(
    client: AsyncClient, sessionmaker: Session, count: int
) -> tuple[Account, list[str]]:
    account, zone, media = await seller(sessionmaker)
    ids: list[str] = []
    for index in range(count):
        photo_id = media if index == 0 else await photo(sessionmaker, account.id)
        response = await create(
            client, account, draft(zone, [photo_id], title=f"Robe numéro {index}")
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return account, ids


async def test_newest_first_with_cover(client: AsyncClient, sessionmaker: Session) -> None:
    account, ids = await _drafts(client, sessionmaker, 3)
    page = (await _mine(client, account)).json()
    assert [item["id"] for item in page["data"]] == ids[::-1]
    assert (page["next_cursor"], page["has_more"]) == (None, False)
    first = page["data"][0]
    assert set(first) >= {"id", "short_id", "status", "title", "price", "cover", "version"}
    assert first["status"] == "draft" and first["cover"][0]["format"] == "webp"


async def test_pages_follow_the_cursor(client: AsyncClient, sessionmaker: Session) -> None:
    account, ids = await _drafts(client, sessionmaker, 5)
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = (await _mine(client, account, **params)).json()
        seen += [item["id"] for item in page["data"]]
        assert len(page["data"]) <= 2
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        cursor = page["next_cursor"]
    assert seen == ids[::-1]  # every listing once, in order


async def test_status_filter_and_deleted_left_out(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, ids = await _drafts(client, sessionmaker, 3)
    async with sessionmaker() as db:
        await db.execute(text("UPDATE listings SET status = 'active' WHERE id = :l"), {"l": ids[0]})
        await db.execute(
            text("UPDATE listings SET deleted_at = now() WHERE id = :l"), {"l": ids[1]}
        )
        await db.commit()
    active = (await _mine(client, account, status="active")).json()["data"]
    assert [item["id"] for item in active] == [ids[0]]
    everything = (await _mine(client, account)).json()["data"]
    assert [item["id"] for item in everything] == [ids[2], ids[0]]


async def test_only_the_callers_listings(client: AsyncClient, sessionmaker: Session) -> None:
    _, ids = await _drafts(client, sessionmaker, 2)
    other = await make_account(sessionmaker, completed=True)
    page = (await _mine(client, other)).json()
    assert not {item["id"] for item in page["data"]} & set(ids)


async def test_bad_parameters_refused(client: AsyncClient, sessionmaker: Session) -> None:
    account, _ = await _drafts(client, sessionmaker, 1)
    for params in ({"limit": 0}, {"limit": 101}, {"status": "lost"}, {"cursor": "pas-un-curseur"}):
        response = await _mine(client, account, **params)
        assert response.status_code == 422, params
    anonymous = await client.get("/v1/me/listings")
    assert anonymous.status_code == 401
