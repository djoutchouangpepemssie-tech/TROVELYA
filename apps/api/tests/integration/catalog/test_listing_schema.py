"""Listing tables (P2-T03a1 and T03a2, section 7.5 with the P2 plan additions E5, E8, E10, E14).

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


async def _checked_at_commit(conn: AsyncConnection) -> str:
    return await _fails(conn, text("SET CONSTRAINTS ALL IMMEDIATE"), {})


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


async def _photo(conn: AsyncConnection, owner: UUID) -> UUID:
    media_id = new_id()
    await conn.execute(
        text(
            "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
            " status) VALUES (:id, :owner, 'image', 'listing', :key, 'image/jpeg', 10,"
            " 'uploading')"
        ),
        {"id": media_id, "owner": owner, "key": new_id().hex},
    )
    return media_id


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


async def test_listing_media_ordered_and_owned_by_one_listing(
    conn: AsyncConnection, seller: UUID, category: UUID
) -> None:
    listing_id = await _listing(conn, seller, category)
    other = await _listing(conn, seller, category, short_id="Zz9yY8xX7w")
    first, second = await _photo(conn, seller), await _photo(conn, seller)
    insert = text("INSERT INTO listing_media (listing_id, media_id, position) VALUES (:l, :m, :p)")
    await conn.execute(insert, {"l": listing_id, "m": first, "p": 0})
    await conn.execute(insert, {"l": listing_id, "m": second, "p": 1})
    # Reordered within one transaction: positions are checked at commit.
    await conn.execute(
        text("UPDATE listing_media SET position = 1 - position WHERE listing_id = :l"),
        {"l": listing_id},
    )
    await conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    assert "listing_media_media_id_key" in await _fails(
        conn, insert, {"l": other, "m": first, "p": 0}
    )
    assert "listing_media_position_check" in await _fails(
        conn, insert, {"l": other, "m": await _photo(conn, seller), "p": -1}
    )
    await conn.execute(insert, {"l": other, "m": await _photo(conn, seller), "p": 0})
    await conn.execute(insert, {"l": other, "m": await _photo(conn, seller), "p": 0})
    assert "listing_media_position_key" in await _checked_at_commit(conn)


async def test_favorites_and_price_watches(
    conn: AsyncConnection, seller: UUID, category: UUID
) -> None:
    listing_id = await _listing(conn, seller, category)
    favorite = text("INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)")
    await conn.execute(favorite, {"u": seller, "l": listing_id})
    assert "favorites_pkey" in await _fails(conn, favorite, {"u": seller, "l": listing_id})
    watch = text(
        "INSERT INTO price_watches (user_id, listing_id, target_minor) VALUES (:u, :l, :t)"
    )
    assert "price_watches_target_minor_check" in await _fails(
        conn, watch, {"u": seller, "l": listing_id, "t": 0}
    )
    await conn.execute(watch, {"u": seller, "l": listing_id, "t": None})


async def test_price_history(conn: AsyncConnection, seller: UUID, category: UUID) -> None:
    listing_id = await _listing(conn, seller, category)
    insert = text("INSERT INTO listing_price_history (listing_id, price_minor) VALUES (:l, :p)")
    await conn.execute(insert, {"l": listing_id, "p": 4500})
    assert "listing_price_history_price_minor_check" in await _fails(
        conn, insert, {"l": listing_id, "p": 99}
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"actor_kind": "robot"}, "listing_status_history_actor_kind_check"),
        ({"to_status": "online"}, "invalid input value for enum listing_status"),
        ({"event": "Publish!"}, "listing_status_history_event_check"),
        ({"actor_kind": "user", "actor_id": None}, "listing_status_history_actor_check"),
        ({"reason_text": "x" * 1001}, "listing_status_history_reason_text_check"),
    ],
)
async def test_status_history_checks(
    conn: AsyncConnection,
    seller: UUID,
    category: UUID,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    listing_id = await _listing(conn, seller, category)
    params = {
        "id": new_id(),
        "listing_id": listing_id,
        "from_status": "draft",
        "to_status": "active",
        "event": "publish",
        "actor_id": seller,
        "actor_kind": "user",
        "reason_code": None,
        "reason_text": None,
    } | overrides
    insert = text(
        "INSERT INTO listing_status_history (id, listing_id, from_status, to_status, event,"
        " actor_id, actor_kind, reason_code, reason_text) VALUES (:id, :listing_id,"
        " CAST(:from_status AS listing_status), CAST(:to_status AS listing_status), :event,"
        " :actor_id, :actor_kind, :reason_code, :reason_text)"
    )
    assert constraint in await _fails(conn, insert, params)
    # A transition made by the system needs no actor; a creation has no previous status.
    await conn.execute(
        insert,
        params
        | {
            "id": new_id(),
            "from_status": None,
            "to_status": "draft",
            "event": "create",
            "actor_id": None,
            "actor_kind": "system",
            "reason_code": "auto_moderation",
            "reason_text": None,
        },
    )


async def test_deleting_a_listing_deletes_what_hangs_on_it(
    conn: AsyncConnection, seller: UUID, category: UUID
) -> None:
    listing_id = await _listing(conn, seller, category)
    photo = await _photo(conn, seller)
    for statement in (
        "INSERT INTO listing_media (listing_id, media_id, position) VALUES (:l, :m, 0)",
        "INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)",
        "INSERT INTO price_watches (user_id, listing_id) VALUES (:u, :l)",
        "INSERT INTO listing_price_history (listing_id, price_minor) VALUES (:l, 4500)",
        "INSERT INTO listing_status_history (id, listing_id, to_status, event, actor_kind)"
        " VALUES (:h, :l, 'draft', 'create', 'system')",
    ):
        await conn.execute(
            text(statement), {"l": listing_id, "m": photo, "u": seller, "h": new_id()}
        )
    await conn.execute(text("DELETE FROM listings WHERE id = :l"), {"l": listing_id})
    for table in (
        "listing_media",
        "favorites",
        "price_watches",
        "listing_price_history",
        "listing_status_history",
    ):
        count = await conn.scalar(
            text(f"SELECT count(*) FROM {table} WHERE listing_id = :l"),  # noqa: S608
            {"l": listing_id},
        )
        assert count == 0, table
    # The photo itself stays: the media purge decides what becomes of it.
    assert await conn.scalar(text("SELECT count(*) FROM media WHERE id = :m"), {"m": photo}) == 1


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
