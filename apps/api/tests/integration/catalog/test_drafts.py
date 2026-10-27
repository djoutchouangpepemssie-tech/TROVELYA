"""`POST /v1/listings`: a new draft (P2-T03b2b2, section 11.5). The rules a draft follows are
tested in test_draft_rules; here, the route: what it writes, what it answers, what it refuses.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.catalog.test_categories_api import (
    catalog_client,
    seeded,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_draft_rules import photo
from tests.integration.identity.test_member_location import make_address, make_zone
from tests.integration.identity.test_profile import Account, make_account
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]


@pytest.fixture
async def client(
    seeded: None,  # noqa: F811
    sessionmaker: Session,
    redis_client: Redis,
) -> AsyncIterator[AsyncClient]:
    async with await catalog_client(sessionmaker, redis_client, verticals=False) as c:
        yield c


async def seller(sessionmaker: Session) -> tuple[Account, UUID, UUID]:
    """A completed member with a zone and one ready listing photo."""
    account = await make_account(sessionmaker, completed=True)
    zone = await make_zone(sessionmaker, account.id)
    return account, zone, await photo(sessionmaker, account.id)


def draft(zone: UUID, media_ids: list[UUID], **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Robe en lin bleue",
        "description": "Portée deux fois, aucune tache, coupe droite.",
        "category": "mode.femme.robes",
        "condition": "very_good",
        "attributes": {"clothing_size": "m", "color": "bleu"},
        "price": {"amount_minor": 2500, "currency": "EUR"},
        "location": {"source": "zone", "id": str(zone)},
        "media_ids": [str(m) for m in media_ids],
    }
    return body | changes


async def create(client: AsyncClient, account: Account, body: dict[str, Any]) -> Any:
    headers = account.headers | {"idempotency-key": str(new_id())}
    return await client.post("/v1/listings", headers=headers, json=body)


async def test_draft_created(client: AsyncClient, sessionmaker: Session) -> None:
    account, zone, media = await seller(sessionmaker)
    second = await photo(sessionmaker, account.id)
    response = await create(client, account, draft(zone, [media, second], brand="Sézane"))
    assert response.status_code == 201, response.text
    listing = response.json()
    assert listing["status"] == "draft"
    assert listing["version"] == 1
    assert len(listing["short_id"]) == 10 and listing["short_id"].isalnum()
    assert listing["title"] == "Robe en lin bleue"
    assert listing["category"] == "mode.femme.robes"
    assert listing["brand"] == "Sézane"
    assert listing["attributes"] == {"clothing_size": "m", "color": "bleu"}
    assert listing["price"] == {"amount_minor": 2500, "currency": "EUR"}
    assert listing["place_name"] == "Lyon 7e"
    assert listing["location"] == {"source": "zone", "id": str(zone)}
    assert listing["media_ids"] == [str(media), str(second)]
    async with sessionmaker() as db:
        prices = (
            (
                await db.execute(
                    text("SELECT price_minor FROM listing_price_history WHERE listing_id = :l"),
                    {"l": listing["id"]},
                )
            )
            .scalars()
            .all()
        )
        brand = (
            await db.execute(text("SELECT is_verified FROM brands WHERE name = 'Sézane'"))
        ).scalar_one()
    assert prices == [2500]  # the history starts with the first price
    assert brand is False  # an unknown brand is created unverified (Q3)


async def test_no_coordinates_in_the_response(client: AsyncClient, sessionmaker: Session) -> None:
    account, zone, media = await seller(sessionmaker)
    response = await create(client, account, draft(zone, [media]))
    body = response.text
    assert response.status_code == 201
    assert not {"lat", "lon", "latitude", "longitude", "location_public", "h3_r7", "h3_r9"} & set(
        response.json()
    )
    assert "45.74" not in body and "4.84" not in body


async def test_create_idempotent(client: AsyncClient, sessionmaker: Session) -> None:
    account, zone, media = await seller(sessionmaker)
    headers = account.headers | {"idempotency-key": str(new_id())}
    first = await client.post("/v1/listings", headers=headers, json=draft(zone, [media]))
    again = await client.post("/v1/listings", headers=headers, json=draft(zone, [media]))
    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json()["id"] == first.json()["id"]
    assert again.headers["idempotent-replayed"] == "true"
    missing = await client.post("/v1/listings", headers=account.headers, json=draft(zone, [media]))
    assert missing.status_code == 400
    assert missing.json()["code"] == "idempotency_key_required"


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"category": "mode.femme"}, 422, "category_not_leaf"),
        ({"brand": "日本"}, 422, "brand_invalid"),
        (
            {"category": "culture_loisirs.instruments.pianos", "attributes": {}},
            422,
            "shipping_not_allowed",
        ),
    ],
)
async def test_rules_answered_as_problems(
    client: AsyncClient, sessionmaker: Session, changes: dict[str, Any], status: int, code: str
) -> None:
    """The rules themselves are tested in test_draft_rules; here, how the route answers."""
    account, zone, media = await seller(sessionmaker)
    response = await create(client, account, draft(zone, [media]) | changes)
    assert (response.status_code, response.json()["code"]) == (status, code)


async def test_attributes_checked_all_at_once(client: AsyncClient, sessionmaker: Session) -> None:
    account, zone, media = await seller(sessionmaker)
    body = draft(zone, [media], attributes={"color": "fuchsia", "storage_gb": "g128"})
    response = await create(client, account, body)
    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "invalid_attributes"
    assert sorted((e["field"], e["code"]) for e in problem["errors"]) == [
        ("attributes.clothing_size", "required"),
        ("attributes.color", "not_in_list"),
        ("attributes.storage_gb", "unknown"),  # an attribute of another category
    ]


async def test_photo_of_another_member_404(client: AsyncClient, sessionmaker: Session) -> None:
    account, zone, media = await seller(sessionmaker)
    other = await make_account(sessionmaker, completed=True)
    response = await create(
        client, account, draft(zone, [media, await photo(sessionmaker, other.id)])
    )
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


async def test_photo_in_another_listing_and_too_many(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, zone, media = await seller(sessionmaker)
    assert (await create(client, account, draft(zone, [media]))).status_code == 201
    reused = await create(client, account, draft(zone, [media]))
    assert (reused.status_code, reused.json()["code"]) == (409, "media_in_use")
    thirteen = [await photo(sessionmaker, account.id) for _ in range(13)]  # 12 for clothes
    too_many = await create(client, account, draft(zone, thirteen))
    assert (too_many.status_code, too_many.json()["code"]) == (422, "media_limit")
    twice = await create(client, account, draft(zone, [thirteen[0], thirteen[0]]))
    assert twice.status_code == 422


async def test_location_must_be_the_sellers(client: AsyncClient, sessionmaker: Session) -> None:
    account, _, media = await seller(sessionmaker)
    other = await make_account(sessionmaker, completed=True)
    others_zone = await make_zone(sessionmaker, other.id)
    response = await create(client, account, draft(others_zone, [media]))
    assert (response.status_code, response.json()["code"]) == (422, "location_unavailable")
    address = await make_address(sessionmaker, account.id)
    body = draft(others_zone, [media], location={"source": "address", "id": str(address)})
    created = await create(client, account, body)
    assert created.status_code == 201
    assert created.json()["place_name"] == "Villeurbanne"


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "   Robe   "},  # 4 characters once trimmed
        {"title": "Robe\nbleue en lin"},
        {"description": "Courte\x00description bien longue"},
        {"price": {"amount_minor": 99, "currency": "EUR"}},
        {"price": {"amount_minor": 2500, "currency": "USD"}},
        {"price": {"amount_minor": 25.5, "currency": "EUR"}},
        {"media_ids": []},
        {"sale_modes": ["auction"]},  # not a field of a draft yet
    ],
)
async def test_body_refused(
    client: AsyncClient, sessionmaker: Session, changes: dict[str, Any]
) -> None:
    account, zone, media = await seller(sessionmaker)
    response = await create(client, account, draft(zone, [media]) | changes)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


async def test_profile_must_be_completed(client: AsyncClient, sessionmaker: Session) -> None:
    account = await make_account(sessionmaker, completed=False)
    zone = await make_zone(sessionmaker, account.id)
    media = await photo(sessionmaker, account.id)
    response = await create(client, account, draft(zone, [media]))
    assert response.status_code == 403
