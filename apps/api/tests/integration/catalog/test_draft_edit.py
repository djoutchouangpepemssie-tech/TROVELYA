"""`PATCH /v1/listings/{id}`: a draft changed by its seller (P2-T03b2c, section 11.1 and 11.5).

`If-Match` is mandatory (428 without it, 412 when stale); the same rules as at creation apply
to the draft as it becomes; a new price joins the history; another member's listing is 404.
Only drafts change for now: an edited active listing goes back through moderation (P2-T05) and
pushes its expiry (P2-T04).
"""

import json
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import text

from tests.integration.catalog.test_categories_api import (
    seeded,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_draft_rules import photo
from tests.integration.catalog.test_drafts import (
    Session,
    client,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
    create,
    draft,
    seller,
)
from tests.integration.identity.test_member_location import make_address
from tests.integration.identity.test_profile import Account, make_account


async def _patch(
    client: AsyncClient,  # noqa: F811
    account: Account,
    listing: dict[str, Any],
    changes: dict[str, Any],
    *,
    version: int | str | None = None,
) -> Response:
    headers = dict(account.headers) | {"content-type": "application/json"}
    if version != "none":
        headers["if-match"] = str(listing["version"] if version is None else version)
    return await client.patch(
        f"/v1/listings/{listing['id']}", headers=headers, content=json.dumps(changes)
    )


async def _draft(client: AsyncClient, sessionmaker: Session) -> tuple[Account, dict[str, Any]]:  # noqa: F811
    account, zone, media = await seller(sessionmaker)
    response = await create(client, account, draft(zone, [media]))
    assert response.status_code == 201, response.text
    return account, response.json()


async def test_fields_changed_version_bumped(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    account, listing = await _draft(client, sessionmaker)
    response = await _patch(
        client,
        account,
        listing,
        {"title": "  Robe en lin bleu nuit ", "brand": "Sézane", "weight_g": 300},
    )
    assert response.status_code == 200, response.text
    edited = response.json()
    assert (edited["title"], edited["brand"], edited["weight_g"]) == (
        "Robe en lin bleu nuit",
        "Sézane",
        300,
    )
    assert edited["version"] == listing["version"] + 1
    # What was not sent stays as it was.
    assert {k: edited[k] for k in ("description", "attributes", "price", "media_ids")} == {
        k: listing[k] for k in ("description", "attributes", "price", "media_ids")
    }
    removed = await _patch(client, account, edited, {"brand": None, "weight_g": None})
    assert removed.status_code == 200, removed.text
    assert (removed.json()["brand"], removed.json()["weight_g"]) == (None, None)


async def test_if_match_required_and_checked(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    account, listing = await _draft(client, sessionmaker)
    missing = await _patch(client, account, listing, {"title": "Robe bleue"}, version="none")
    assert (missing.status_code, missing.json()["code"]) == (428, "precondition_required")
    assert (await _patch(client, account, listing, {"title": "Robe bleue"})).status_code == 200
    stale = await _patch(client, account, listing, {"title": "Robe rouge"})  # old version
    assert (stale.status_code, stale.json()["code"]) == (412, "precondition_failed")
    for odd in ("abc", '"1"x', ""):
        answer = await _patch(client, account, listing, {"title": "Robe rouge"}, version=odd)
        assert answer.status_code in (412, 428), odd
    weak = await _patch(client, account, listing, {"title": "Robe verte"}, version='W/"2"')
    assert weak.status_code == 200, weak.text


async def test_price_change_recorded(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    account, listing = await _draft(client, sessionmaker)
    first = await _patch(client, account, listing, {"price": {"amount_minor": 2000}})
    same = await _patch(client, account, first.json(), {"price": {"amount_minor": 2000}})
    assert (first.status_code, same.status_code) == (200, 200)
    async with sessionmaker() as db:
        prices = (
            await db.execute(
                text(
                    "SELECT price_minor FROM listing_price_history WHERE listing_id = :l"
                    " ORDER BY changed_at, id"
                ),
                {"l": listing["id"]},
            )
        ).scalars()
        assert list(prices) == [2500, 2000]  # an unchanged price adds nothing


async def test_rules_apply_to_the_draft_as_it_becomes(
    client: AsyncClient,  # noqa: F811
    sessionmaker: Session,
) -> None:
    account, listing = await _draft(client, sessionmaker)
    # A smartphone needs a storage and a brand: the dress's attributes do not fit.
    phone = "high_tech.telephones.smartphones"
    attributes = await _patch(client, account, listing, {"category": phone})
    assert (attributes.status_code, attributes.json()["code"]) == (422, "invalid_attributes")
    brand = await _patch(
        client, account, listing, {"category": phone, "attributes": {"storage_gb": "g128"}}
    )
    assert (brand.status_code, brand.json()["code"]) == (422, "brand_required")
    refused = await _patch(client, account, listing, {"title": None})
    assert (refused.status_code, refused.json()["code"]) == (422, "validation_error")
    unknown = await _patch(client, account, listing, {"status": "active"})
    assert unknown.status_code == 422
    # Nothing was written by the refused changes.
    again = await _patch(client, account, listing, {})
    assert again.status_code == 200 and again.json()["version"] == listing["version"]


async def test_photos_and_place_replaced(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    account, listing = await _draft(client, sessionmaker)
    new_photos = [str(await photo(sessionmaker, account.id)) for _ in range(2)]
    address = await make_address(sessionmaker, account.id)
    response = await _patch(
        client,
        account,
        listing,
        {"media_ids": new_photos, "location": {"source": "address", "id": str(address)}},
    )
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["media_ids"] == new_photos
    assert (edited["place_name"], edited["location"]["source"]) == ("Villeurbanne", "address")
    # The photo taken off the draft can go to another one.
    other = await _patch(client, account, edited, {"media_ids": listing["media_ids"]})
    assert other.status_code == 200
    assert other.json()["media_ids"] == listing["media_ids"]


async def test_other_members_listing_404(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    _, listing = await _draft(client, sessionmaker)
    intruder = await make_account(sessionmaker, completed=True)
    response = await _patch(client, intruder, listing, {"title": "Robe volée"})
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


async def test_only_drafts_change_for_now(client: AsyncClient, sessionmaker: Session) -> None:  # noqa: F811
    account, listing = await _draft(client, sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = 'active' WHERE id = :l"), {"l": listing["id"]}
        )
        await db.commit()
    response = await _patch(
        client, account, listing, {"title": "Robe bleue"}, version=listing["version"] + 1
    )
    assert (response.status_code, response.json()["code"]) == (409, "listing_not_editable")
