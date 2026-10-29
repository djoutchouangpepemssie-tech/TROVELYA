"""`GET /v1/listings/{id}/price-history` (P2-T08b, plan Q43): the prices shown online, from the
first time online; a draft's or an offline listing's answer is 404, as if it did not exist."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_draft_edit import _draft, _patch  # pyright: ignore[reportPrivateUsage]
from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.service.prices import lowest_price_30_days


async def test_price_history_from_first_online(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    """Q43: never the prices tried in the draft; anybody reads, signed in or not."""
    seller, draft = await _draft(client, sessionmaker)
    path = f"/v1/listings/{draft['id']}/price-history"
    assert (await client.get(path)).status_code == 404  # a draft
    changed = await _patch(
        client, seller, draft, {"price": {"amount_minor": 1900, "currency": "EUR"}}
    )
    assert changed.status_code == 200, changed.text
    assert (await _call(client, seller, draft["id"], "publish")).status_code == 200
    history = await client.get(path)
    assert history.status_code == 200, history.text
    [point] = history.json()["prices"]
    assert point["price"] == {"amount_minor": 1900, "currency": "EUR"}
    await _call(client, seller, draft["id"], "withdraw")
    assert (await client.get(path)).status_code == 404


async def test_back_online_one_point_and_hidden_seller(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    """Withdrawn then put back online at the same price: one point, dated the first time
    online; a seller no longer shown: 404."""
    seller, draft = await _draft(client, sessionmaker)
    published = await _call(client, seller, draft["id"], "publish")
    await _call(client, seller, draft["id"], "withdraw")
    assert (await _call(client, seller, draft["id"], "renew")).status_code == 200
    path = f"/v1/listings/{draft['id']}/price-history"
    [point] = (await client.get(path)).json()["prices"]
    assert point["at"] == published.json()["published_at"]
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE users SET status = 'suspended' WHERE id = :u"), {"u": seller.id}
        )
        await db.commit()
    assert (await client.get(path)).status_code == 404


async def test_lowest_price_30_days_from_the_database(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    seller, draft = await _draft(client, sessionmaker)
    await _call(client, seller, draft["id"], "publish")
    async with sessionmaker() as db:
        now = await db.scalar(text("SELECT now()"))
        await repository.record_price(db, draft["id"], 1500, now + timedelta(days=1))
        await db.commit()
        assert await lowest_price_30_days(db, draft["id"], now + timedelta(days=2)) == 1500
        assert await lowest_price_30_days(db, draft["id"], now + timedelta(days=1)) == 2500
