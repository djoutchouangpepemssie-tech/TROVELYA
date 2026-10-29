"""Favorites and price watches (P2-T08, section 11.5, plan Q43): only on someone else's listing
online, idempotent, the listing's favorite count kept exact in the same transaction; watching
a price is favoring the listing."""

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text

from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_review_queue import (
    _in_review,  # pyright: ignore[reportPrivateUsage]
    _listing,  # pyright: ignore[reportPrivateUsage]
)
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from tests.integration.identity.test_profile import Account, make_account

PRICED = {"price": {"amount_minor": 12000, "currency": "EUR"}}


async def _member(sessionmaker: Session) -> Account:
    return await make_account(sessionmaker, completed=True)


async def _send(
    client: AsyncClient,  # noqa: F811
    account: Account,
    method: str,
    listing_id: str,
    what: str = "favorite",
    body: Any = None,
) -> Response:
    path = f"/v1/listings/{listing_id}/{what}"
    return await client.request(method, path, headers=account.headers, json=body)


async def _sql(sessionmaker: Session, sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        value = (await db.execute(text(sql), params)).scalar() if sql.startswith("SELECT") else None
        if not sql.startswith("SELECT"):
            await db.execute(text(sql), params)
        await db.commit()
    return value


async def _count(sessionmaker: Session, listing_id: str) -> int:
    sql = "SELECT favorite_count FROM listings WHERE id = :l"
    return int(await _sql(sessionmaker, sql, l=listing_id))


async def _favorites(client: AsyncClient, member: Account, **params: str) -> Any:  # noqa: F811
    return (await client.get("/v1/me/favorites", headers=member.headers, params=params)).json()


async def test_favorite_idempotent_and_counted(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    _, listing = await _listing(client, sessionmaker)
    member = await _member(sessionmaker)
    for _ in range(2):
        assert (await _send(client, member, "POST", listing["id"])).status_code == 204
    assert await _count(sessionmaker, listing["id"]) == 1
    for _ in range(2):
        assert (await _send(client, member, "DELETE", listing["id"])).status_code == 204
    assert await _count(sessionmaker, listing["id"]) == 0


async def test_cannot_favorite_own_or_inactive(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """Own listing online: 409 (favorite and watch); offline or unknown: 404, and a favorite is
    always taken back (the listing may have left meanwhile)."""
    seller, listing = await _listing(client, sessionmaker)
    for what in ("favorite", "price-watch"):
        own = await _send(client, seller, "POST", listing["id"], what, {})
        assert (own.status_code, own.json()["code"]) == (409, "own_listing")
    member = await _member(sessionmaker)
    await _send(client, member, "POST", listing["id"])
    assert (await _call(client, seller, listing["id"], "withdraw")).status_code == 200
    for what in ("favorite", "price-watch"):
        assert (await _send(client, member, "POST", listing["id"], what, {})).status_code == 404
    assert (await _send(client, seller, "POST", listing["id"])).status_code == 404
    unknown = await _send(client, member, "POST", "01a18434-f2fe-740a-ba0b-58d6b5aefec2")
    assert unknown.status_code == 404
    assert (await _send(client, member, "DELETE", listing["id"])).status_code == 204
    assert await _count(sessionmaker, listing["id"]) == 0
    _, pending = await _in_review(client, sessionmaker)
    assert (await _send(client, member, "POST", pending["id"])).status_code == 404


async def test_concurrent_favorites_count_exact(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    _, listing = await _listing(client, sessionmaker)
    members = [await _member(sessionmaker) for _ in range(6)]
    calls = [_send(client, m, "POST", listing["id"]) for m in members for _ in range(2)]
    assert {r.status_code for r in await asyncio.gather(*calls)} == {204}
    assert await _count(sessionmaker, listing["id"]) == 6
    calls = [_send(client, m, "DELETE", listing["id"]) for m in members[:4] for _ in range(2)]
    calls += [_send(client, m, "POST", listing["id"]) for m in members[4:]]
    await asyncio.gather(*calls)
    assert await _count(sessionmaker, listing["id"]) == 2


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({}, 204),
        ({"target_minor": 100}, 204),
        ({"target_minor": 11999}, 204),
        ({"target_minor": 99}, 422),
        ({"target_minor": 12000}, 422),
        ({"target_minor": 0}, 422),
        ({"target_minor": True}, 422),
        ({"target_minor": 100.0}, 422),
        ({"target": 500}, 422),
    ],
)
async def test_price_watch_target_bounds(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
    body: dict[str, Any],
    status: int,
) -> None:
    """Q43: from 1 € (the lowest price) to below the current price (12 000 here)."""
    _, listing = await _listing(client, sessionmaker, **PRICED)
    member = await _member(sessionmaker)
    answer = await _send(client, member, "POST", listing["id"], "price-watch", body)
    assert answer.status_code == status, answer.text


async def test_watching_is_favoring(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """Q43: a watch puts the listing in favorites (target replaced when sent again); taking the
    watch back keeps the favorite, taking the favorite back stops the watch."""
    _, listing = await _listing(client, sessionmaker, **PRICED)
    member = await _member(sessionmaker)
    for target in (9000, 8000):
        body = {"target_minor": target}
        await _send(client, member, "POST", listing["id"], "price-watch", body)
    [item] = (await _favorites(client, member))["data"]
    assert (item["id"], item["available"], item["price_watch"]) == (
        listing["id"],
        True,
        {"target_minor": 8000},
    )
    assert await _count(sessionmaker, listing["id"]) == 1
    await _send(client, member, "DELETE", listing["id"], "price-watch")
    assert (await _favorites(client, member))["data"][0]["price_watch"] is None
    await _send(client, member, "POST", listing["id"], "price-watch", {})
    await _send(client, member, "DELETE", listing["id"])
    watches = "SELECT count(*) FROM price_watches WHERE listing_id = :l"
    assert await _sql(sessionmaker, watches, l=listing["id"]) == 0
    assert await _count(sessionmaker, listing["id"]) == 0


async def test_hidden_seller_and_removed(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """A seller no longer shown: 404, the favorite unavailable; a listing removed by the
    moderation: listed without title nor price."""
    seller, listing = await _listing(client, sessionmaker)
    _, removed = await _listing(client, sessionmaker)
    member = await _member(sessionmaker)
    for one in (listing, removed):
        await _send(client, member, "POST", one["id"])
    await _sql(sessionmaker, "UPDATE users SET status = 'suspended' WHERE id = :u", u=seller.id)
    await _sql(
        sessionmaker, "UPDATE listings SET status = 'removed' WHERE id = :l", l=removed["id"]
    )
    assert (
        await _send(client, member, "POST", listing["id"], "price-watch", {})
    ).status_code == 404
    items = (await _favorites(client, member, available="false"))["data"]
    shown = [(i["id"], i["available"], i["title"], i["price"] is None) for i in items]
    assert shown == [
        (removed["id"], False, None, True),
        (listing["id"], False, listing["title"], False),
    ]
    assert (await _favorites(client, member))["data"] == []


async def test_my_favorites_pages(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    member = await _member(sessionmaker)
    listings = [(await _listing(client, sessionmaker))[1] for _ in range(5)]
    for listing in listings:
        await _send(client, member, "POST", listing["id"])
    left = [listings[1]["id"], listings[3]["id"]]
    await _sql(
        sessionmaker, "UPDATE listings SET status = 'withdrawn' WHERE id = ANY(:ids)", ids=left
    )
    seen: list[str] = []
    cursor = None
    while True:
        page = await _favorites(client, member, limit="2", **({"cursor": cursor} if cursor else {}))
        seen += [item["id"] for item in page["data"]]
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        cursor = page["next_cursor"]
    assert seen == [listings[i]["id"] for i in (4, 2, 0)]  # available, the latest first
    others = await _favorites(client, member, available="false")
    assert [item["id"] for item in others["data"]] == left[::-1]
    bad = await client.get("/v1/me/favorites", headers=member.headers, params={"cursor": "x"})
    assert bad.status_code == 422
    empty = await _favorites(client, await _member(sessionmaker))
    assert empty == {"data": [], "next_cursor": None, "has_more": False}
