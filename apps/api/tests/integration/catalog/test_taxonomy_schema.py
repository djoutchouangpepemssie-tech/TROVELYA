"""Category, attribute and brand tables (P2-T01a, section 7.5 with the P2 plan additions)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trovelya.shared.ids import new_id

_INSERT_CATEGORY = text(
    "INSERT INTO categories (id, parent_id, key, path, names, vertical, transaction_model,"
    " brand_policy, allowed_conditions)"
    " VALUES (:id, :parent_id, :key, text2ltree(CAST(:key AS text)), CAST(:names AS jsonb),"
    " :vertical, :model, :brand_policy, CAST(:conditions AS item_condition[]))"
)
_INSERT_ATTRIBUTE = text(
    "INSERT INTO attribute_definitions (id, key, names, data_type, enum_values, constraints)"
    ' VALUES (:id, :key, \'{"fr":"x"}\', :data_type, CAST(:enum_values AS jsonb),'
    " CAST(:constraints AS jsonb))"
)


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose work is always rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


async def _category(conn: AsyncConnection, key: str, **overrides: Any) -> Any:
    values = {
        "id": new_id(),
        "parent_id": None,
        "key": key,
        "names": '{"fr":"Catégorie"}',
        "vertical": "goods",
        "model": "protected_purchase",
        "brand_policy": "optional",
        "conditions": None,
    } | overrides
    await conn.execute(_INSERT_CATEGORY, values)
    return values["id"]


async def _fails(conn: AsyncConnection, statement: Any, params: dict[str, Any]) -> str:
    """Run a statement expected to fail inside a savepoint; return the error message."""
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(statement, params)
    await savepoint.rollback()
    return str(error.value)


async def test_category_defaults_follow_the_spec(conn: AsyncConnection) -> None:
    category_id = await _category(conn, "t_defaults")
    row = (
        await conn.execute(
            text(
                "SELECT is_active, is_restricted, shipping_allowed, max_photos, vat_category,"
                " position FROM categories WHERE id = :id"
            ),
            {"id": category_id},
        )
    ).one()
    assert tuple(row) == (True, False, True, 12, "standard", 0)


async def test_category_key_unique(conn: AsyncConnection) -> None:
    await _category(conn, "t_unique")
    message = await _fails(
        conn,
        _INSERT_CATEGORY,
        {
            "id": new_id(),
            "parent_id": None,
            "key": "t_unique",
            "names": "{}",
            "vertical": "goods",
            "model": "contact",
            "brand_policy": "none",
            "conditions": None,
        },
    )
    assert "categories_key_key" in message


async def test_path_is_ltree_and_descendants_found(conn: AsyncConnection) -> None:
    root = await _category(conn, "t_tree")
    child = await _category(conn, "t_tree.child", parent_id=root)
    await _category(conn, "t_tree.child.leaf", parent_id=child)
    await _category(conn, "t_other")
    rows = await conn.execute(
        text("SELECT key FROM categories WHERE path <@ 't_tree' ORDER BY path")
    )
    assert [r[0] for r in rows] == ["t_tree", "t_tree.child", "t_tree.child.leaf"]


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("vertical", "cars", "categories_vertical_check"),
        ("model", "auction", "categories_transaction_model_check"),
        ("brand_policy", "sometimes", "categories_brand_policy_check"),
    ],
)
async def test_category_checks(
    conn: AsyncConnection, column: str, value: str, constraint: str
) -> None:
    params = {
        "id": new_id(),
        "parent_id": None,
        "key": f"t_check_{column}",
        "names": "{}",
        "vertical": "goods",
        "model": "protected_purchase",
        "brand_policy": "optional",
        "conditions": None,
    } | {column: value}
    assert constraint in await _fails(conn, _INSERT_CATEGORY, params)


async def test_key_must_match_path(conn: AsyncConnection) -> None:
    message = await _fails(
        conn,
        text("INSERT INTO categories (id, key, path, names) VALUES (:id, 't_a', 't_b', '{}')"),
        {"id": new_id()},
    )
    assert "categories_path_matches_key" in message


async def test_allowed_conditions_use_the_condition_type(conn: AsyncConnection) -> None:
    await _category(conn, "t_cosmetics", conditions=["new_with_tags", "new_without_tags"])
    message = await _fails(
        conn,
        _INSERT_CATEGORY,
        {
            "id": new_id(),
            "parent_id": None,
            "key": "t_bad_condition",
            "names": "{}",
            "vertical": "goods",
            "model": "protected_purchase",
            "brand_policy": "optional",
            "conditions": ["like_new"],
        },
    )
    assert "invalid input value for enum item_condition" in message


async def test_max_photos_bounds(conn: AsyncConnection) -> None:
    category_id = await _category(conn, "t_photos")
    message = await _fails(
        conn,
        text("UPDATE categories SET max_photos = 0 WHERE id = :id"),
        {"id": category_id},
    )
    assert "categories_max_photos_check" in message


async def test_enum_attribute_needs_values(conn: AsyncConnection) -> None:
    await conn.execute(
        _INSERT_ATTRIBUTE,
        {
            "id": new_id(),
            "key": "t_color",
            "data_type": "enum",
            "enum_values": '{"noir":{"fr":"Noir"}}',
            "constraints": "{}",
        },
    )
    message = await _fails(
        conn,
        _INSERT_ATTRIBUTE,
        {
            "id": new_id(),
            "key": "t_enum_empty",
            "data_type": "enum",
            "enum_values": None,
            "constraints": "{}",
        },
    )
    assert "attribute_definitions_enum_values_check" in message


async def test_attribute_data_type_check(conn: AsyncConnection) -> None:
    message = await _fails(
        conn,
        _INSERT_ATTRIBUTE,
        {
            "id": new_id(),
            "key": "t_date",
            "data_type": "date",
            "enum_values": None,
            "constraints": "{}",
        },
    )
    assert "attribute_definitions_data_type_check" in message


async def test_category_attribute_link(conn: AsyncConnection) -> None:
    category_id = await _category(conn, "t_link")
    attribute_id = new_id()
    await conn.execute(
        _INSERT_ATTRIBUTE,
        {
            "id": attribute_id,
            "key": "t_size",
            "data_type": "text",
            "enum_values": None,
            "constraints": '{"max_length":10}',
        },
    )
    link = text(
        "INSERT INTO category_attributes (category_id, attribute_id, is_required)"
        " VALUES (:c, :a, true)"
    )
    await conn.execute(link, {"c": category_id, "a": attribute_id})
    message = await _fails(conn, link, {"c": category_id, "a": attribute_id})
    assert "category_attributes_pkey" in message


async def test_brand_name_citext_unique(conn: AsyncConnection) -> None:
    insert = text("INSERT INTO brands (id, name, slug) VALUES (:id, :name, :slug)")
    await conn.execute(insert, {"id": new_id(), "name": "Apple", "slug": "apple"})
    message = await _fails(conn, insert, {"id": new_id(), "name": "apple", "slug": "apple-2"})
    assert "brands_name_key" in message


async def test_brand_slug_format(conn: AsyncConnection) -> None:
    message = await _fails(
        conn,
        text("INSERT INTO brands (id, name, slug) VALUES (:id, 'Hermès', 'Hermès')"),
        {"id": new_id()},
    )
    assert "brands_slug_check" in message


async def test_listing_enums_exist(conn: AsyncConnection) -> None:
    rows = await conn.execute(
        text(
            "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)"
            " FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid"
            " WHERE t.typname IN ('listing_status','item_condition') GROUP BY t.typname"
        )
    )
    assert dict(rows.all()) == {
        "item_condition": [
            "new_with_tags",
            "new_without_tags",
            "very_good",
            "good",
            "fair",
            "for_parts",
        ],
        "listing_status": [
            "draft",
            "pending_review",
            "active",
            "reserved",
            "sold",
            "withdrawn",
            "removed",
            "expired",
        ],
    }
