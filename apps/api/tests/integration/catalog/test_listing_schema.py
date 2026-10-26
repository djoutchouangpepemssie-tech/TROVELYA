"""Listings table (P2-T03a1, section 7.5 with the P2 plan additions E5, E10, E14).

Every constraint of the migration has a case below.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trovelya.shared.ids import new_id

_INSERT_LISTING = text(
    "INSERT INTO listings (id, short_id, seller_id, title, description, category_id, condition,"
    " attributes, price_minor, currency, original_price_minor, quantity, min_offer_minor,"
    " parcel_size, weight_g, location, location_public, h3_r7, h3_r9, place_name,"
    " country_code, location_source, location_source_id, sale_modes, quality_score,"
    " embedding, embedding_model, view_count, favorite_count)"
    " VALUES (:id, :short_id, :seller_id, :title, :description, :category_id, :condition,"
    " CAST(:attributes AS jsonb), :price, :currency, :original_price, :quantity, :min_offer,"
    " :parcel_size, :weight_g, ST_GeogFromText('POINT(4.84 45.75)'),"
    " ST_GeogFromText('POINT(4.85 45.76)'), 608819013654478847, 627333812236304383,"
    " :place_name, :country_code, :location_source, :location_source_id,"
    " CAST(:sale_modes AS text[]), :quality_score, CAST(:embedding AS vector),"
    " :embedding_model, :view_count, :favorite_count)"
)
_SHORT_ID = "Ab3dE5gH9k"


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose work is always rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


async def _fails(conn: AsyncConnection, statement: Any, params: dict[str, Any]) -> str:
    """Run a statement expected to fail inside a savepoint; return the error message."""
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(statement, params)
    await savepoint.rollback()
    return str(error.value)


@pytest.fixture
async def seller(conn: AsyncConnection) -> UUID:
    user_id = new_id()
    await conn.execute(
        text(
            "INSERT INTO users (id, email, username, display_name)"
            " VALUES (:id, :email, :username, 'Vendeuse')"
        ),
        {"id": user_id, "email": f"{user_id.hex}@example.org", "username": f"v_{user_id.hex[:8]}"},
    )
    return user_id


@pytest.fixture
async def category(conn: AsyncConnection) -> UUID:
    category_id = new_id()
    await conn.execute(
        text(
            "INSERT INTO categories (id, key, path, names)"
            " VALUES (:id, 't_listing', 't_listing', '{\"fr\":\"x\"}')"
        ),
        {"id": category_id},
    )
    return category_id


def _listing_params(seller: UUID, category: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_id(),
        "short_id": _SHORT_ID,
        "seller_id": seller,
        "title": "Lampe opaline verte",
        "description": "Lampe opaline des années 1950, abat-jour intact, fonctionne.",
        "category_id": category,
        "condition": "very_good",
        "attributes": "{}",
        "price": 4500,
        "currency": "EUR",
        "original_price": None,
        "quantity": 1,
        "min_offer": None,
        "parcel_size": "m",
        "weight_g": 1200,
        "place_name": "Lyon 7e",
        "country_code": "FR",
        "location_source": "zone",
        "location_source_id": new_id(),
        "sale_modes": ["fixed_price"],
        "quality_score": 0,
        "embedding": None,
        "embedding_model": None,
        "view_count": 0,
        "favorite_count": 0,
    } | overrides


async def _listing(conn: AsyncConnection, seller: UUID, category: UUID, **overrides: Any) -> UUID:
    params = _listing_params(seller, category, **overrides)
    await conn.execute(_INSERT_LISTING, params)
    return params["id"]


async def test_listing_defaults_follow_the_spec(
    conn: AsyncConnection, seller: UUID, category: UUID
) -> None:
    listing_id = await _listing(conn, seller, category)
    row = await conn.execute(
        text(
            "SELECT status, currency, quantity, accepts_offers, handover_enabled,"
            " shipping_enabled, sale_modes, open_to_swap, quality_score, version, attributes,"
            " deleted_at IS NULL FROM listings WHERE id = :id"
        ),
        {"id": listing_id},
    )
    assert tuple(row.one()) == (
        "draft",
        "EUR",
        1,
        True,
        True,
        True,
        ["fixed_price"],
        False,
        0,
        1,
        {},
        True,
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"short_id": "Ab3dE5gH9"}, "listings_short_id_check"),
        ({"short_id": "Ab3dE5gH9k1"}, "listings_short_id_check"),
        ({"short_id": "Ab3dE5gH9-"}, "listings_short_id_check"),
        ({"title": "Lamp"}, "listings_title_check"),
        ({"title": "x" * 121}, "listings_title_check"),
        ({"description": "Trop court."}, "listings_description_check"),
        ({"description": "x" * 5001}, "listings_description_check"),
        ({"condition": "like_new"}, "invalid input value for enum item_condition"),
        ({"attributes": "[]"}, "listings_attributes_check"),
        ({"price": 99}, "listings_price_minor_check"),
        ({"price": 100_000_001}, "listings_price_minor_check"),
        ({"currency": "eur"}, "listings_currency_check"),
        ({"original_price": 0}, "listings_original_price_minor_check"),
        ({"quantity": -1}, "listings_quantity_check"),
        ({"min_offer": 0}, "listings_min_offer_check"),
        ({"min_offer": 4501}, "listings_min_offer_check"),
        ({"parcel_size": "xxl"}, "listings_parcel_size_check"),
        ({"weight_g": 0}, "listings_weight_g_check"),
        ({"place_name": ""}, "listings_place_name_check"),
        ({"country_code": "fr"}, "listings_country_code_check"),
        ({"location_source": "gps"}, "listings_location_source_check"),
        ({"sale_modes": []}, "listings_sale_modes_check"),
        ({"sale_modes": ["fixed_price", "barter"]}, "listings_sale_modes_check"),
        ({"sale_modes": [None]}, "listings_sale_modes_check"),
        ({"quality_score": 101}, "listings_quality_score_check"),
        ({"quality_score": -1}, "listings_quality_score_check"),
        ({"view_count": -1}, "listings_view_count_check"),
        ({"favorite_count": -1}, "listings_favorite_count_check"),
        ({"embedding_model": "titan-v2"}, "listings_embedding_model_check"),
        (
            {"embedding": "[" + ",".join(["0.1"] * 1024) + "]"},
            "listings_embedding_model_check",
        ),
        ({"embedding": "[0.1,0.2]", "embedding_model": "m"}, "expected 1024 dimensions"),
    ],
)
async def test_listing_checks(
    conn: AsyncConnection,
    seller: UUID,
    category: UUID,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    params = _listing_params(seller, category, **overrides)
    assert constraint in await _fails(conn, _INSERT_LISTING, params)


async def test_listing_accepts_its_full_shape(
    conn: AsyncConnection, seller: UUID, category: UUID
) -> None:
    await _listing(
        conn,
        seller,
        category,
        original_price=6000,
        min_offer=4500,
        sale_modes=["fixed_price", "auction", "live", "drop", "group_buy"],
        quality_score=100,
        embedding="[" + ",".join(["0.1"] * 1024) + "]",
        embedding_model="amazon.titan-embed-text-v2:0",
        location_source="address",
    )


async def test_short_id_unique(conn: AsyncConnection, seller: UUID, category: UUID) -> None:
    await _listing(conn, seller, category)
    message = await _fails(conn, _INSERT_LISTING, _listing_params(seller, category))
    assert "listings_short_id_key" in message


async def test_listing_needs_a_known_seller_and_category(
    conn: AsyncConnection, seller: UUID, category: UUID
) -> None:
    for overrides, constraint in (
        ({"seller_id": new_id()}, "listings_seller_id_fkey"),
        ({"category_id": new_id()}, "listings_category_id_fkey"),
    ):
        params = _listing_params(seller, category, **overrides)
        assert constraint in await _fails(conn, _INSERT_LISTING, params)


async def test_version_and_updated_at_follow_each_update(
    conn: AsyncConnection, seller: UUID, category: UUID
) -> None:
    listing_id = await _listing(conn, seller, category)
    await conn.execute(
        text("UPDATE listings SET updated_at = now() - interval '1 day' WHERE id = :id"),
        {"id": listing_id},
    )
    await conn.execute(
        text("UPDATE listings SET price_minor = 4000 WHERE id = :id"), {"id": listing_id}
    )
    version, fresh = (
        await conn.execute(
            text(
                "SELECT version, updated_at > now() - interval '1 minute' FROM listings"
                " WHERE id = :id"
            ),
            {"id": listing_id},
        )
    ).one()
    assert (version, fresh) == (3, True)


async def test_indexes_of_the_spec(conn: AsyncConnection) -> None:
    rows = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'listings'"))
    names = {row[0] for row in rows}
    assert {
        "listings_active_geo_idx",
        "listings_active_h3_idx",
        "listings_title_trgm_idx",
        "listings_seller_idx",
        "listings_category_idx",
        "listings_attributes_idx",
    } <= names
    # P3 creates the full-text index, T11 the vector one.
    assert not names & {"listings_search_idx", "listings_embedding_idx"}
