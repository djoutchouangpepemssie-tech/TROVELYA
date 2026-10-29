"""`GET /v1/listings/{id}/price-history` (P2-T08b, plan Q43): the prices shown online, from the
first time online; a draft's or an offline listing's answer is 404, as if it did not exist."""

from httpx import AsyncClient

from tests.integration.catalog.test_draft_edit import _draft, _patch  # pyright: ignore[reportPrivateUsage]
from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]


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
