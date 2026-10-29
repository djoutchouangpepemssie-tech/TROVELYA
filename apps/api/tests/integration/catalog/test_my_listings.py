"""`GET /v1/me/listings`: the seller's own listings (P2-T03b3b, section 11.3 and 11.5), newest
first, any status (deleted ones left out), cursor pagination `{data, next_cursor, has_more}`."""

import base64
import json
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_draft_rules import photo
from tests.integration.catalog.test_drafts import Session, create, draft, seller
from tests.integration.identity.test_profile import Account


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
    first, first_ids = await _drafts(client, sessionmaker, 3)
    second, second_ids = await _drafts(client, sessionmaker, 2)
    response = await _mine(client, second)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == second_ids[::-1]
    # A cursor of another seller is only a position: the caller's own listings still.
    cursor = (await _mine(client, first, limit=1)).json()["next_cursor"]
    replayed = (await _mine(client, second, cursor=cursor)).json()["data"]
    assert not {item["id"] for item in replayed} & set(first_ids)


async def test_same_creation_time_paged_by_id(client: AsyncClient, sessionmaker: Session) -> None:
    account, ids = await _drafts(client, sessionmaker, 5)
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE listings SET created_at = '2026-10-29 10:00:00.123456+00'"
                " WHERE id = ANY(:i)"
            ),
            {"i": ids},
        )
        await db.commit()
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = (await _mine(client, account, **params)).json()
        seen += [item["id"] for item in page["data"]]
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
    assert seen == sorted(ids, reverse=True)  # ties broken by id, each once


async def test_cover_is_the_first_photo_still_shown(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, zone, first = await seller(sessionmaker)
    second = await photo(sessionmaker, account.id)
    created = (await create(client, account, draft(zone, [first, second]))).json()
    async with sessionmaker() as db:
        await db.execute(text("UPDATE media SET deleted_at = now() WHERE id = :m"), {"m": first})
        await db.commit()
    item = (await _mine(client, account)).json()["data"][0]
    assert item["id"] == created["id"]
    assert item["cover"] is not None and item["cover"][0]["url"].endswith(
        await _variant_key(sessionmaker, second)
    )
    page = (await client.get(f"/v1/listings/{created['id']}", headers=account.headers)).json()
    assert len(page["photos"]) == 1  # the page skips the removed one too


async def _variant_key(sessionmaker: Session, media_id: object) -> str:
    async with sessionmaker() as db:
        variants = await db.scalar(
            text("SELECT variants FROM media WHERE id = :m"), {"m": media_id}
        )
    return variants[0]["key"]


async def test_list_walks_an_index(sessionmaker: Session) -> None:
    """The whole list and the filtered one each follow an index, never a sort of everything."""
    queries = (
        "EXPLAIN SELECT id FROM listings"
        " WHERE seller_id = '01a18434-f2fe-740a-ba0b-58d6b5aefec2' AND deleted_at IS NULL"
        " AND (created_at, id) < ('2100-01-01+00', 'ffffffff-ffff-ffff-ffff-ffffffffffff')"
        " ORDER BY created_at DESC, id DESC LIMIT 25",
        "EXPLAIN SELECT id FROM listings"
        " WHERE seller_id = '01a18434-f2fe-740a-ba0b-58d6b5aefec2' AND deleted_at IS NULL"
        " AND status = 'draft'"
        " AND (created_at, id) < ('2100-01-01+00', 'ffffffff-ffff-ffff-ffff-ffffffffffff')"
        " ORDER BY created_at DESC, id DESC LIMIT 25",
    )
    async with sessionmaker() as db:
        await db.execute(text("SET LOCAL enable_seqscan = off"))
        for query in queries:
            plan = "\n".join((await db.execute(text(query))).scalars())
            assert "Sort" not in plan, plan
            assert "listings_seller" in plan, plan


async def test_bad_parameters_refused(client: AsyncClient, sessionmaker: Session) -> None:
    account, _ = await _drafts(client, sessionmaker, 1)
    forged: list[object] = [
        ["2026-01-01T00:00:00+00:00", 1],
        ["2026-01-01T00:00:00+00:00", {}],
        ["0001-01-01T00:00:00+23:59", "01a18434-f2fe-740a-ba0b-58d6b5aefec2"],
        ["9999-12-31T23:59:59-23:59", "01a18434-f2fe-740a-ba0b-58d6b5aefec2"],
        ["2026-01-01", "01a18434-f2fe-740a-ba0b-58d6b5aefec2"],  # no time zone
        ["2026-01-01T00:00:00+00:00", "pas-un-uuid"],
        {"at": 1},
        None,
    ]
    cursors = ["pas-un-curseur"] + [
        base64.urlsafe_b64encode(json.dumps(value).encode()).decode() for value in forged
    ]
    for params in [{"limit": 0}, {"limit": 101}, {"status": "lost"}] + [
        {"cursor": c} for c in cursors
    ]:
        response = await _mine(client, account, **params)
        assert response.status_code == 422, params
    anonymous = await client.get("/v1/me/listings")
    assert anonymous.status_code == 401
