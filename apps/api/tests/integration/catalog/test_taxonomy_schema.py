"""Category, attribute and brand tables (P2-T01a, section 7.5 with the P2 plan additions)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from trovelya.modules.catalog.models import ItemCondition, ListingStatus
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
            "names": '{"fr":"x"}',
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
        "names": '{"fr":"x"}',
        "vertical": "goods",
        "model": "protected_purchase",
        "brand_policy": "optional",
        "conditions": None,
    } | {column: value}
    assert constraint in await _fails(conn, _INSERT_CATEGORY, params)


async def test_path_must_end_with_key_label(conn: AsyncConnection) -> None:
    message = await _fails(
        conn,
        text(
            "INSERT INTO categories (id, key, path, names)"
            " VALUES (:id, 't_a', 't_b', '{\"fr\":\"x\"}')"
        ),
        {"id": new_id()},
    )
    assert "categories_path_ends_with_key" in message


async def test_moved_category_keeps_its_key(conn: AsyncConnection) -> None:
    old_parent = await _category(conn, "t_old")
    new_parent = await _category(conn, "t_new")
    moved = await _category(conn, "t_old.leaf", parent_id=old_parent)
    await conn.execute(
        text("UPDATE categories SET parent_id = :p, path = 't_new.leaf' WHERE id = :id"),
        {"p": new_parent, "id": moved},
    )
    row = (await conn.execute(text("SELECT key FROM categories WHERE path = 't_new.leaf'"))).one()
    assert row[0] == "t_old.leaf"


async def test_path_unique(conn: AsyncConnection) -> None:
    parent = await _category(conn, "t_dup")
    await _category(conn, "t_dup.leaf", parent_id=parent)
    await conn.execute(text("SET CONSTRAINTS categories_path_key IMMEDIATE"))
    message = await _fails(
        conn,
        text(
            "INSERT INTO categories (id, parent_id, key, path, names)"
            " VALUES (:id, :p, 't_elsewhere.leaf', 't_dup.leaf', '{\"fr\":\"x\"}')"
        ),
        {"id": new_id(), "p": parent},
    )
    assert "categories_path_key" in message


async def test_allowed_conditions_use_the_condition_type(conn: AsyncConnection) -> None:
    await _category(conn, "t_cosmetics", conditions=["new_with_tags", "new_without_tags"])
    message = await _fails(
        conn,
        _INSERT_CATEGORY,
        {
            "id": new_id(),
            "parent_id": None,
            "key": "t_bad_condition",
            "names": '{"fr":"x"}',
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
            "enum_values": '[{"key":"noir","names":{"fr":"Noir"}}]',
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
    await conn.execute(insert, {"id": new_id(), "name": "Marque Témoin", "slug": "marque-temoin"})
    message = await _fails(
        conn, insert, {"id": new_id(), "name": "marque témoin", "slug": "marque-temoin-2"}
    )
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
        "item_condition": [c.value for c in ItemCondition],
        "listing_status": [st.value for st in ListingStatus],
    }


_INSERT_RAW = text(
    "INSERT INTO categories (id, parent_id, key, path, names, allowed_conditions,"
    " protected_payment_cap_minor)"
    " VALUES (:id, :parent_id, :key, text2ltree(:path), CAST(:names AS jsonb),"
    " CAST(:conditions AS item_condition[]), :cap)"
)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"key": "T_Upper", "path": "T_Upper"}, "categories_key_check"),
        ({"key": "t-dash", "path": "t-dash"}, "categories_key_check"),
        ({"key": "t_lvl.two", "path": "t_lvl.two"}, "categories_root_has_no_parent"),
        ({"conditions": []}, "categories_allowed_conditions_check"),
        ({"conditions": [None]}, "categories_allowed_conditions_check"),
        ({"cap": 0}, "categories_protected_payment_cap_minor_check"),
        ({"names": "{}"}, "categories_names_check"),
        ({"names": '["fr"]'}, "categories_names_check"),
    ],
)
async def test_more_category_checks(
    conn: AsyncConnection, overrides: dict[str, Any], constraint: str
) -> None:
    params = {
        "id": new_id(),
        "parent_id": None,
        "key": "t_raw",
        "path": "t_raw",
        "names": '{"fr":"x"}',
        "conditions": None,
        "cap": None,
    } | overrides
    assert constraint in await _fails(conn, _INSERT_RAW, params)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"key": "Size"}, "attribute_definitions_key_check"),
        ({"key": "1size"}, "attribute_definitions_key_check"),
        ({"enum_values": "[]"}, "attribute_definitions_enum_values_check"),
        ({"enum_values": '{"a":{"fr":"A"}}'}, "attribute_definitions_enum_values_check"),
        (
            {"data_type": "text", "enum_values": '[{"key":"a","names":{"fr":"A"}}]'},
            "attribute_definitions_enum_values_check",
        ),
        ({"data_type": "text", "enum_values": "[1]"}, "attribute_definitions_enum_values_check"),
    ],
)
async def test_more_attribute_checks(
    conn: AsyncConnection, overrides: dict[str, Any], constraint: str
) -> None:
    params = {
        "id": new_id(),
        "key": "t_attr",
        "data_type": "enum",
        "enum_values": '[{"key":"a","names":{"fr":"A"}}]',
        "constraints": "{}",
    } | overrides
    assert constraint in await _fails(conn, _INSERT_ATTRIBUTE, params)


@pytest.mark.parametrize("name", ["", "x" * 81])
async def test_brand_name_length(conn: AsyncConnection, name: str) -> None:
    message = await _fails(
        conn,
        text("INSERT INTO brands (id, name, slug) VALUES (:id, :name, 'slug')"),
        {"id": new_id(), "name": name},
    )
    assert "brands_name_check" in message


async def _immediate_fails(conn: AsyncConnection) -> str:
    return await _fails(conn, text("SET CONSTRAINTS ALL IMMEDIATE"), {})


async def test_category_must_sit_under_its_parent(conn: AsyncConnection) -> None:
    first = await _category(conn, "t_pa")
    await _category(conn, "t_pb")
    await conn.execute(
        _INSERT_RAW,
        {
            "id": new_id(),
            "parent_id": first,
            "key": "t_pb.x",
            "path": "t_pb.x",
            "names": '{"fr":"x"}',
            "conditions": None,
            "cap": None,
        },
    )
    assert "categories_tree_check" in await _immediate_fails(conn)


async def test_category_cannot_be_its_own_parent(conn: AsyncConnection) -> None:
    parent = await _category(conn, "t_self")
    child = await _category(conn, "t_self.child", parent_id=parent)
    await conn.execute(text("UPDATE categories SET parent_id = id WHERE id = :id"), {"id": child})
    assert "categories_tree_check" in await _immediate_fails(conn)


async def test_moving_a_node_moves_its_subtree(conn: AsyncConnection) -> None:
    old_root = await _category(conn, "t_from")
    new_root = await _category(conn, "t_to")
    middle = await _category(conn, "t_from.mid", parent_id=old_root)
    leaf = await _category(conn, "t_from.mid.leaf", parent_id=middle)
    await _category(conn, "t_from.mid.leaf.deep", parent_id=leaf)
    await conn.execute(
        text("UPDATE categories SET parent_id = :p, path = 't_to.mid' WHERE id = :id"),
        {"p": new_root, "id": middle},
    )
    await conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    rows = await conn.execute(
        text("SELECT key, path::text FROM categories WHERE key LIKE 't_from.mid%' ORDER BY key")
    )
    assert [tuple(r) for r in rows] == [
        ("t_from.mid", "t_to.mid"),
        ("t_from.mid.leaf", "t_to.mid.leaf"),
        ("t_from.mid.leaf.deep", "t_to.mid.leaf.deep"),
    ]


async def test_two_nodes_swap_places_in_one_transaction(conn: AsyncConnection) -> None:
    left = await _category(conn, "t_left")
    right = await _category(conn, "t_right")
    a = await _category(conn, "t_left.same", parent_id=left)
    await _category(conn, "t_left.same.child", parent_id=a)
    b = await _category(conn, "t_right.same", parent_id=right)
    await conn.execute(
        text("UPDATE categories SET parent_id = :p, path = 't_right.same' WHERE id = :id"),
        {"p": right, "id": a},
    )
    await conn.execute(
        text("UPDATE categories SET parent_id = :p, path = 't_left.same' WHERE id = :id"),
        {"p": left, "id": b},
    )
    await conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    child = await conn.execute(
        text("SELECT path::text FROM categories WHERE key = 't_left.same.child'")
    )
    assert child.scalar_one() == "t_right.same.child"


async def test_category_rows_cannot_be_deleted_with_their_attributes(
    conn: AsyncConnection,
) -> None:
    category_id = await _category(conn, "t_del")
    attribute_id = new_id()
    await conn.execute(
        _INSERT_ATTRIBUTE,
        {
            "id": attribute_id,
            "key": "t_del_attr",
            "data_type": "bool",
            "enum_values": None,
            "constraints": "{}",
        },
    )
    await conn.execute(
        text("INSERT INTO category_attributes (category_id, attribute_id) VALUES (:c, :a)"),
        {"c": category_id, "a": attribute_id},
    )
    message = await _fails(conn, text("DELETE FROM categories WHERE id = :id"), {"id": category_id})
    assert "category_attributes_category_id_fkey" in message
