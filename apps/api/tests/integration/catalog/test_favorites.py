"""Favorites and price watches (P2-T08, section 11.5, plan Q43): only on someone else's listing
online, idempotent, the listing's favorite count kept exact in the same transaction."""

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text

from tests.integration.catalog.test_draft_edit import _draft, _patch  # pyright: ignore[reportPrivateUsage]
from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_review_queue import _listing  # pyright: ignore[reportPrivateUsage]
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from tests.integration.identity.test_profile import Account, make_account


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


async def _count(sessionmaker: Session, listing_id: str) -> int:
    async with sessionmaker() as db:
        found = await db.scalar(
            text("SELECT favorite_count FROM listings WHERE id = :l"), {"l": listing_id}
        )
    return int(found)


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
    seller, listing = await _listing(client, sessionmaker)
    own = await _send(client, seller, "POST", listing["id"])
    assert (own.status_code, own.json()["code"]) == (409, "own_listing")
    assert (await _call(client, seller, listing["id"], "withdraw")).status_code == 200
    member = await _member(sessionmaker)
    for what in ("favorite", "price-watch"):
        gone = await _send(client, member, "POST", listing["id"], what, {})
        assert gone.status_code == 404, what
    unknown = await _send(client, member, "POST", "01a18434-f2fe-740a-ba0b-58d6b5aefec2")
    assert unknown.status_code == 404


async def test_unfavorite_a_listing_gone_offline(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    """Taking a favorite away always works: the listing may have left in the meantime."""
    seller, listing = await _listing(client, sessionmaker)
    member = await _member(sessionmaker)
    await _send(client, member, "POST", listing["id"])
    await _call(client, seller, listing["id"], "withdraw")
    assert (await _send(client, member, "DELETE", listing["id"])).status_code == 204
    assert await _count(sessionmaker, listing["id"]) == 0


async def test_concurrent_favorites_count_exact(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    _, listing = await _listing(client, sessionmaker)
    members = [await _member(sessionmaker) for _ in range(6)]
    calls = [_send(client, m, "POST", listing["id"]) for m in members for _ in range(2)]
    assert {r.status_code for r in await asyncio.gather(*calls)} == {204}
    assert await _count(sessionmaker, listing["id"]) == 6
    calls = [_send(client, m, "DELETE", listing["id"]) for m in members[:4] for _ in range(2)]
    await asyncio.gather(*calls)
    assert await _count(sessionmaker, listing["id"]) == 2


@pytest.mark.parametrize(
    ("target", "status"),
    [(None, 204), (100, 204), (11999, 204), (99, 422), (12000, 422), (0, 422), (-5, 422)],
)
async def test_price_watch_target_bounds(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
    target: int | None,
    status: int,
) -> None:
    """Q43: from 1 € (the lowest price) to below the current price (12 000 here)."""
    _, listing = await _listing(
        client, sessionmaker, price={"amount_minor": 12000, "currency": "EUR"}
    )
    member = await _member(sessionmaker)
    body = {} if target is None else {"target_minor": target}
    answer = await _send(client, member, "POST", listing["id"], "price-watch", body)
    assert answer.status_code == status, answer.text


async def test_price_watch_kept_once_and_updated(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    _, listing = await _listing(
        client, sessionmaker, price={"amount_minor": 12000, "currency": "EUR"}
    )
    member = await _member(sessionmaker)
    for target in (9000, 8000):
        body = {"target_minor": target}
        assert (
            await _send(client, member, "POST", listing["id"], "price-watch", body)
        ).status_code == 204
    async with sessionmaker() as db:
        rows = (
            await db.execute(
                text("SELECT target_minor FROM price_watches WHERE listing_id = :l"),
                {"l": listing["id"]},
            )
        ).all()
    assert [tuple(r) for r in rows] == [(8000,)]
    assert (await _send(client, member, "DELETE", listing["id"], "price-watch")).status_code == 204


async def test_my_favorites_available_first(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    _, kept = await _listing(client, sessionmaker)
    _, gone = await _listing(client, sessionmaker)
    member = await _member(sessionmaker)
    for listing in (kept, gone):
        await _send(client, member, "POST", listing["id"])
    await _send(client, member, "POST", kept["id"], "price-watch", {"target_minor": 500})
    async with sessionmaker() as db:  # the second one leaves (withdrawn by its seller)
        await db.execute(
            text("UPDATE listings SET status = 'withdrawn' WHERE id = :l"), {"l": gone["id"]}
        )
        await db.commit()
    available = await client.get("/v1/me/favorites", headers=member.headers)
    assert available.status_code == 200, available.text
    [item] = available.json()["data"]
    assert (item["id"], item["available"], item["price_watch"]) == (
        kept["id"],
        True,
        {"target_minor": 500},
    )
    assert {"title", "price", "cover", "favorited_at"} <= set(item)
    others = await client.get(
        "/v1/me/favorites", headers=member.headers, params={"available": "false"}
    )
    assert [(i["id"], i["available"]) for i in others.json()["data"]] == [(gone["id"], False)]


async def test_price_history_from_first_online(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """Q43: the prices shown online only, never the ones tried in the draft; anybody reads."""
    seller, draft = await _draft(client, sessionmaker)
    hidden = await client.get(f"/v1/listings/{draft['id']}/price-history")
    assert hidden.status_code == 404  # a draft: as if it did not exist
    changed = await _patch(
        client, seller, draft, {"price": {"amount_minor": 1900, "currency": "EUR"}}
    )
    assert changed.status_code == 200, changed.text
    assert (await _call(client, seller, draft["id"], "publish")).status_code == 200
    history = await client.get(f"/v1/listings/{draft['id']}/price-history")
    assert history.status_code == 200, history.text
    [point] = history.json()["prices"]
    assert point["price"] == {"amount_minor": 1900, "currency": "EUR"}
    await _call(client, seller, draft["id"], "withdraw")
    assert (await client.get(f"/v1/listings/{draft['id']}/price-history")).status_code == 404
