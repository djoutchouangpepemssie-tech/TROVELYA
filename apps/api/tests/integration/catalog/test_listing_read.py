"""`GET /v1/listings/{id}`: the listing page (P2-T03b3a, section 11.5, 8.11, plan P2 Q13, Q17,
E13). An active listing is read by anybody; any other only by its seller (404 for the others).
Never a coordinate: the place name, and for a signed-in visitor with a zone a distance computed
on the public position and rounded. A seller in erasure grace, suspended or banned is nobody's
to read.
"""

import json
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_drafts import (
    Session,
    create,
    draft,
    seller,
)
from tests.integration.identity.test_member_location import make_zone
from tests.integration.identity.test_profile import Account, make_account


async def _listing(
    client: AsyncClient, sessionmaker: Session, *, active: bool = True
) -> tuple[Account, dict[str, Any]]:
    account, zone, media = await seller(sessionmaker)
    response = await create(client, account, draft(zone, [media], brand="Sézane"))
    assert response.status_code == 201, response.text
    listing = response.json()
    if active:
        await _status(sessionmaker, listing["id"], "active")
    return account, listing


async def _status(sessionmaker: Session, listing_id: str, status: str) -> None:
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = CAST(:s AS listing_status) WHERE id = :l"),
            {"s": status, "l": listing_id},
        )
        await db.commit()


async def _read(client: AsyncClient, listing_id: str, account: Account | None = None) -> Any:
    return await client.get(
        f"/v1/listings/{listing_id}", headers=account.headers if account else {}
    )


async def test_active_listing_read_by_anybody(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _listing(client, sessionmaker)
    response = await _read(client, listing["id"])
    assert response.status_code == 200, response.text
    page = response.json()
    assert (page["id"], page["short_id"], page["title"], page["status"]) == (
        listing["id"],
        listing["short_id"],
        "Robe en lin bleue",
        "active",
    )
    assert page["category"] == {"key": "mode.femme.robes", "name": "Robes"}
    assert page["brand"] == "Sézane"
    assert page["price"] == {"amount_minor": 2500, "currency": "EUR"}
    assert page["place_name"] == "Lyon 7e"
    assert page["distance"] is None  # nobody signed in (Q17)
    # Attributes named for display: the key, its label, the value and the value's label.
    assert {a["key"]: (a["name"], a["value"], a["value_name"]) for a in page["attributes"]} == {
        "clothing_size": ("Taille", "m", "M"),
        "color": ("Couleur", "bleu", "Bleu"),
    }
    assert page["seller"]["username"].startswith("membre_")
    assert set(page["seller"]) == {"id", "username", "display_name", "avatar", "member_since"}
    assert len(page["photos"]) == 1 and page["photos"][0][0]["format"] == "webp"


async def test_no_coordinates_anywhere(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _listing(client, sessionmaker)
    visitor = await make_account(sessionmaker, completed=True)
    await make_zone(sessionmaker, visitor.id, at=(45.76, 4.83), default=True)
    for account in (None, visitor):
        response = await _read(client, listing["id"], account)
        decimals: list[str] = []
        json.loads(response.text, parse_float=decimals.append)
        assert decimals == [], decimals


async def test_distance_on_the_public_position_rounded(
    client: AsyncClient,
    sessionmaker: Session,
) -> None:
    """The visitor stands on the seller's real position: the distance shown is that of the
    public one (200 to 500 m away), so « moins de 1 km », never 0 (E13)."""
    _, listing = await _listing(client, sessionmaker)
    visitor = await make_account(sessionmaker, completed=True)
    await make_zone(sessionmaker, visitor.id, at=(45.74, 4.84), default=True)
    assert (await _read(client, listing["id"], visitor)).json()["distance"] == "moins de 1 km"
    far = await make_account(sessionmaker, completed=True)
    await make_zone(sessionmaker, far.id, at=(48.8566, 2.3522), default=True)  # Paris, about 390 km
    assert (await _read(client, listing["id"], far)).json()["distance"] == "390 km"


async def test_no_distance_without_viewer_zone(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _listing(client, sessionmaker)
    visitor = await make_account(sessionmaker, completed=True)
    await make_zone(sessionmaker, visitor.id, at=(45.9, 5.1))  # not the default one
    assert (await _read(client, listing["id"], visitor)).json()["distance"] is None


async def test_public_position_stable_over_reads(
    client: AsyncClient, sessionmaker: Session
) -> None:
    _, listing = await _listing(client, sessionmaker)
    visitor = await make_account(sessionmaker, completed=True)
    await make_zone(sessionmaker, visitor.id, at=(45.9, 5.1), default=True)
    distances = {
        (await _read(client, listing["id"], visitor)).json()["distance"] for _ in range(50)
    }
    assert len(distances) == 1


async def test_listing_not_active_is_the_sellers_only(
    client: AsyncClient,
    sessionmaker: Session,
) -> None:
    account, listing = await _listing(client, sessionmaker, active=False)
    intruder = await make_account(sessionmaker, completed=True)
    for status in ("draft", "pending_review", "removed", "withdrawn", "expired", "sold"):
        await _status(sessionmaker, listing["id"], status)
        for visitor in (None, intruder):
            response = await _read(client, listing["id"], visitor)
            assert (response.status_code, response.json()["code"]) == (404, "not_found"), status
        own = await _read(client, listing["id"], account)
        assert (own.status_code, own.json()["status"]) == (200, status)


async def test_deleted_or_unknown_listing_404(client: AsyncClient, sessionmaker: Session) -> None:
    account, listing = await _listing(client, sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET deleted_at = now() WHERE id = :l"), {"l": listing["id"]}
        )
        await db.commit()
    for visitor in (None, account):
        assert (await _read(client, listing["id"], visitor)).status_code == 404
    assert (await _read(client, "01a18434-f2fe-740a-ba0b-58d6b5aefec2")).status_code == 404
    assert (await _read(client, "pas-un-uuid")).status_code == 422


async def test_listings_hidden_during_erasure_grace(
    client: AsyncClient,
    sessionmaker: Session,
) -> None:
    """Q13: from the erasure request, the seller's listings are nobody else's to read."""
    account, listing = await _listing(client, sessionmaker)
    await _seller_state(sessionmaker, account.id, "erasure_requested_at = now()")
    assert (await _read(client, listing["id"])).status_code == 404
    assert (await _read(client, listing["id"], account)).status_code == 200  # still theirs


async def test_listings_of_a_suspended_seller_hidden(
    client: AsyncClient,
    sessionmaker: Session,
) -> None:
    account, listing = await _listing(client, sessionmaker)
    await _seller_state(sessionmaker, account.id, "status = 'suspended'")
    assert (await _read(client, listing["id"])).status_code == 404


async def _seller_state(sessionmaker: Session, user_id: UUID, change: str) -> None:
    sql = {
        "erasure_requested_at = now()": (
            "UPDATE users SET erasure_requested_at = now() WHERE id = :u"
        ),
        "status = 'suspended'": "UPDATE users SET status = 'suspended' WHERE id = :u",
    }[change]
    async with sessionmaker() as db:
        await db.execute(text(sql), {"u": user_id})
        await db.commit()
