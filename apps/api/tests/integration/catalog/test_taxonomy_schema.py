"""Category, attribute and brand tables (P2-T01a, section 7.5 with the P2 plan additions).

Every constraint of the migration has a case below (each one checked by mutation).
"""

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
    " brand_policy, allowed_conditions, max_photos, protected_payment_cap_minor)"
    " VALUES (:id, :parent_id, :key, text2ltree(:path), CAST(:names AS jsonb), :vertical,"
    " :model, :brand_policy, CAST(:conditions AS item_condition[]), :max_photos, :cap)"
)
_INSERT_ATTRIBUTE = text(
    "INSERT INTO attribute_definitions (id, key, names, data_type, enum_values, constraints)"
    " VALUES (:id, :key, CAST(:names AS jsonb), :data_type, CAST(:enum_values AS jsonb), '{}')"
)
_INSERT_BRAND = text("INSERT INTO brands (id, name, slug) VALUES (:id, :name, :slug)")
_FR = '{"fr":"x"}'
_VALUES = '[{"key":"noir","names":{"fr":"Noir"}}]'


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose work is always rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


def _category_params(key: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": new_id(),
        "parent_id": None,
        "key": key,
        "path": key,
        "names": _FR,
        "vertical": "goods",
        "model": "protected_purchase",
        "brand_policy": "optional",
        "conditions": None,
        "max_photos": 12,
        "cap": None,
    } | overrides


async def _category(conn: AsyncConnection, key: str, **overrides: Any) -> Any:
    params = _category_params(key, **overrides)
    await conn.execute(_INSERT_CATEGORY, params)
    return params["id"]


def _attribute_params(**overrides: Any) -> dict[str, Any]:
    return {
        "id": new_id(),
        "key": "t_attr",
        "names": _FR,
        "data_type": "enum",
        "enum_values": _VALUES,
    } | overrides


async def _fails(conn: AsyncConnection, statement: Any, params: dict[str, Any]) -> str:
    """Run a statement expected to fail inside a savepoint; return the error message."""
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as error:
        await conn.execute(statement, params)
    await savepoint.rollback()
    return str(error.value)


async def _checked_at_commit(conn: AsyncConnection) -> str:
    """The deferred checks, run now; return the error message."""
    return await _fails(conn, text("SET CONSTRAINTS ALL IMMEDIATE"), {})


async def test_category_defaults_follow_the_spec(conn: AsyncConnection) -> None:
    await conn.execute(
        text("INSERT INTO categories (id, key, path, names) VALUES (:id, 't_def', 't_def', :n)"),
        {"id": new_id(), "n": _FR},
    )
    row = await conn.execute(
        text(
            "SELECT is_active, is_restricted, shipping_allowed, max_photos, vat_category,"
            " position, vertical, transaction_model, brand_policy, allowed_conditions"
            " FROM categories WHERE key = 't_def'"
        )
    )
    assert tuple(row.one()) == (
        True,
        False,
        True,
        12,
        "standard",
        0,
        "goods",
        "protected_purchase",
        "optional",
        None,
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"vertical": "cars"}, "categories_vertical_check"),
        ({"model": "auction"}, "categories_transaction_model_check"),
        ({"brand_policy": "sometimes"}, "categories_brand_policy_check"),
        ({"max_photos": 0}, "categories_max_photos_check"),
        ({"max_photos": 51}, "categories_max_photos_check"),
        ({"key": "T_Upper", "path": "T_Upper"}, "categories_key_check"),
        ({"key": "t-dash", "path": "t-dash"}, "categories_key_check"),
        ({"key": "t_a", "path": "t_b"}, "categories_path_ends_with_key"),
        ({"key": "t_lvl.two", "path": "t_lvl.two"}, "categories_root_has_no_parent"),
        ({"conditions": []}, "categories_allowed_conditions_check"),
        ({"conditions": [None]}, "categories_allowed_conditions_check"),
        ({"conditions": ["like_new"]}, "invalid input value for enum item_condition"),
        ({"cap": 0}, "categories_protected_payment_cap_minor_check"),
        ({"names": "{}"}, "categories_names_check"),
        ({"names": '["fr"]'}, "categories_names_check"),
    ],
)
async def test_category_checks(
    conn: AsyncConnection, overrides: dict[str, Any], constraint: str
) -> None:
    params = _category_params("t_check") | overrides
    assert constraint in await _fails(conn, _INSERT_CATEGORY, params)


async def test_category_accepts_a_condition_list(conn: AsyncConnection) -> None:
    await _category(conn, "t_cosmetics", conditions=["new_with_tags", "new_without_tags"])


async def test_category_key_unique(conn: AsyncConnection) -> None:
    await _category(conn, "t_unique")
    message = await _fails(conn, _INSERT_CATEGORY, _category_params("t_unique"))
    assert "categories_key_key" in message


async def test_path_unique_at_commit(conn: AsyncConnection) -> None:
    parent = await _category(conn, "t_dup")
    await _category(conn, "t_dup.leaf", parent_id=parent, path="t_dup.leaf")
    params = _category_params("t_else.leaf", parent_id=parent, path="t_dup.leaf")
    await conn.execute(_INSERT_CATEGORY, params)  # deferred: accepted for now
    assert "categories_path_key" in await _checked_at_commit(conn)


async def test_descendants_found_by_path(conn: AsyncConnection) -> None:
    root = await _category(conn, "t_tree")
    child = await _category(conn, "t_tree.child", parent_id=root, path="t_tree.child")
    await _category(conn, "t_tree.child.leaf", parent_id=child, path="t_tree.child.leaf")
    await _category(conn, "t_other")
    rows = await conn.execute(
        text("SELECT key FROM categories WHERE path <@ 't_tree' ORDER BY path")
    )
    assert [r[0] for r in rows] == ["t_tree", "t_tree.child", "t_tree.child.leaf"]


async def test_category_must_sit_under_its_parent(conn: AsyncConnection) -> None:
    first = await _category(conn, "t_pa")
    await _category(conn, "t_pb")
    await _category(conn, "t_pb.x", parent_id=first, path="t_pb.x")
    assert "categories_tree_check" in await _checked_at_commit(conn)


async def test_category_cannot_be_its_own_parent(conn: AsyncConnection) -> None:
    parent = await _category(conn, "t_self")
    child = await _category(conn, "t_self.child", parent_id=parent, path="t_self.child")
    await conn.execute(text("UPDATE categories SET parent_id = id WHERE id = :id"), {"id": child})
    assert "categories_tree_check" in await _checked_at_commit(conn)


async def test_moving_a_node_moves_its_subtree_and_keeps_keys(conn: AsyncConnection) -> None:
    old_root = await _category(conn, "t_from")
    new_root = await _category(conn, "t_to")
    middle = await _category(conn, "t_from.mid", parent_id=old_root, path="t_from.mid")
    leaf = await _category(conn, "t_from.mid.leaf", parent_id=middle, path="t_from.mid.leaf")
    await _category(conn, "t_from.mid.leaf.deep", parent_id=leaf, path="t_from.mid.leaf.deep")
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
    a = await _category(conn, "t_left.same", parent_id=left, path="t_left.same")
    await _category(conn, "t_left.same.child", parent_id=a, path="t_left.same.child")
    b = await _category(conn, "t_right.same", parent_id=right, path="t_right.same")
    move = text("UPDATE categories SET parent_id = :p, path = text2ltree(:path) WHERE id = :id")
    await conn.execute(move, {"p": right, "path": "t_right.same", "id": a})
    await conn.execute(move, {"p": left, "path": "t_left.same", "id": b})
    await conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    child = await conn.execute(
        text("SELECT path::text FROM categories WHERE key = 't_left.same.child'")
    )
    assert child.scalar_one() == "t_right.same.child"


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"key": "Size"}, "attribute_definitions_key_check"),
        ({"key": "1size"}, "attribute_definitions_key_check"),
        ({"data_type": "date"}, "attribute_definitions_data_type_check"),
        ({"names": "{}"}, "attribute_definitions_names_check"),
        ({"enum_values": None}, "attribute_definitions_enum_values_check"),
        ({"enum_values": "[]"}, "attribute_definitions_enum_values_check"),
        ({"enum_values": '{"a":{"fr":"A"}}'}, "attribute_definitions_enum_values_check"),
        ({"data_type": "text"}, "attribute_definitions_enum_values_check"),
        ({"data_type": "text", "enum_values": "[1]"}, "attribute_definitions_enum_values_check"),
    ],
)
async def test_attribute_checks(
    conn: AsyncConnection, overrides: dict[str, Any], constraint: str
) -> None:
    assert constraint in await _fails(conn, _INSERT_ATTRIBUTE, _attribute_params(**overrides))


async def test_attribute_accepts_enum_and_plain_types(conn: AsyncConnection) -> None:
    await conn.execute(_INSERT_ATTRIBUTE, _attribute_params(key="t_color"))
    await conn.execute(
        _INSERT_ATTRIBUTE, _attribute_params(key="t_isbn", data_type="text", enum_values=None)
    )


async def test_category_attribute_link(conn: AsyncConnection) -> None:
    category_id = await _category(conn, "t_link")
    attribute = _attribute_params(key="t_size", data_type="bool", enum_values=None)
    await conn.execute(_INSERT_ATTRIBUTE, attribute)
    link = text(
        "INSERT INTO category_attributes (category_id, attribute_id, is_required)"
        " VALUES (:c, :a, true)"
    )
    params = {"c": category_id, "a": attribute["id"]}
    await conn.execute(link, params)
    assert "category_attributes_pkey" in await _fails(conn, link, params)
    # No cascade (section 7.5): a category is never deleted with its attributes.
    message = await _fails(conn, text("DELETE FROM categories WHERE id = :id"), {"id": category_id})
    assert "category_attributes_category_id_fkey" in message


@pytest.mark.parametrize(
    ("name", "slug", "constraint"),
    [
        ("marque témoin", "marque-temoin-2", "brands_name_key"),  # citext: case ignored
        ("Hermès", "Hermès", "brands_slug_check"),
        ("", "vide", "brands_name_check"),
        ("x" * 81, "longue", "brands_name_check"),
    ],
)
async def test_brand_checks(conn: AsyncConnection, name: str, slug: str, constraint: str) -> None:
    await conn.execute(
        _INSERT_BRAND, {"id": new_id(), "name": "Marque Témoin", "slug": "marque-temoin"}
    )
    message = await _fails(conn, _INSERT_BRAND, {"id": new_id(), "name": name, "slug": slug})
    assert constraint in message


async def test_listing_enums_match_the_code(conn: AsyncConnection) -> None:
    rows = await conn.execute(
        text(
            "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)"
            " FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid"
            " WHERE t.typname IN ('listing_status','item_condition') GROUP BY t.typname"
        )
    )
    assert dict(rows.all()) == {
        "item_condition": [c.value for c in ItemCondition],
        "listing_status": [s.value for s in ListingStatus],
    }
