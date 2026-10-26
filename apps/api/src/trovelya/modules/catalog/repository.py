"""SQL of the catalog module. Only this module's service reads or writes these tables."""

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.shared.ids import new_id

_UPSERT_ATTRIBUTE = text(
    "INSERT INTO attribute_definitions (id, key, names, data_type, enum_values, unit, constraints)"
    " VALUES (:id, :key, CAST(:names AS jsonb), :data_type, CAST(:enum_values AS jsonb), :unit,"
    " CAST(:constraints AS jsonb))"
    " ON CONFLICT (key) DO UPDATE SET names = EXCLUDED.names, enum_values = EXCLUDED.enum_values,"
    " unit = EXCLUDED.unit, constraints = EXCLUDED.constraints"
    " RETURNING id"
)

_UPSERT_CATEGORY = text(
    "INSERT INTO categories (id, parent_id, key, path, names, icon, position, is_active,"
    " is_restricted, vertical, transaction_model, shipping_allowed, max_photos,"
    " allowed_conditions, brand_policy)"
    " VALUES (:id, :parent_id, :key, text2ltree(:path), CAST(:names AS jsonb), :icon, :position,"
    " :is_active, :is_restricted, :vertical, :transaction_model, :shipping_allowed, :max_photos,"
    " CAST(:allowed_conditions AS item_condition[]), :brand_policy)"
    " ON CONFLICT (key) DO UPDATE SET parent_id = EXCLUDED.parent_id, path = EXCLUDED.path,"
    " names = EXCLUDED.names, icon = EXCLUDED.icon, position = EXCLUDED.position,"
    " is_active = EXCLUDED.is_active, is_restricted = EXCLUDED.is_restricted,"
    " vertical = EXCLUDED.vertical, transaction_model = EXCLUDED.transaction_model,"
    " shipping_allowed = EXCLUDED.shipping_allowed, max_photos = EXCLUDED.max_photos,"
    " allowed_conditions = EXCLUDED.allowed_conditions, brand_policy = EXCLUDED.brand_policy"
    " RETURNING id"
)

_INSERT_CATEGORY_ATTRIBUTE = text(
    "INSERT INTO category_attributes (category_id, attribute_id, is_required, is_filterable,"
    " position) VALUES (:category_id, :attribute_id, :is_required, :is_filterable, :position)"
)

# Active categories in tree order (parents first, siblings by position); a category is a
# leaf when none of its children is active.
_ACTIVE_CATEGORIES = text(
    "WITH RECURSIVE ordered AS ("
    " SELECT id, ARRAY[position::int] AS sort FROM categories WHERE parent_id IS NULL"
    " UNION ALL"
    " SELECT c.id, o.sort || c.position::int FROM categories c JOIN ordered o ON c.parent_id = o.id"
    ")"
    " SELECT c.id, c.key, p.key AS parent_key, c.names, c.icon, c.position, c.vertical,"
    " c.transaction_model, c.shipping_allowed, c.max_photos, c.is_restricted, c.brand_policy,"
    " c.allowed_conditions::text[] AS allowed_conditions,"
    " NOT EXISTS (SELECT 1 FROM categories ch WHERE ch.parent_id = c.id AND ch.is_active)"
    " AS is_leaf"
    " FROM categories c JOIN ordered o ON o.id = c.id"
    " LEFT JOIN categories p ON p.id = c.parent_id"
    " WHERE c.is_active AND (CAST(:verticals AS boolean) OR c.vertical = 'goods')"
    " ORDER BY o.sort, c.key"
)

_CATEGORY_ATTRIBUTES = text(
    "SELECT ca.category_id, a.key, ca.is_required, ca.is_filterable"
    " FROM category_attributes ca JOIN attribute_definitions a ON a.id = ca.attribute_id"
    " WHERE ca.category_id = ANY(:ids) ORDER BY ca.category_id, ca.position"
)

_ATTRIBUTES = text(
    "SELECT key, names, data_type, enum_values, unit, constraints FROM attribute_definitions"
    " WHERE key = ANY(:keys) ORDER BY key"
)

# Prefix matches first, then the closest names (pg_trgm), on `name::text` so the trigram
# index serves both; the caller escapes LIKE wildcards in the prefix.
_SEARCH_BRANDS = text(
    "SELECT name::text AS name, slug FROM brands"
    " WHERE name::text ILIKE :prefix ESCAPE '\\' OR name::text % :q"
    " ORDER BY name::text ILIKE :prefix ESCAPE '\\' DESC, similarity(name::text, :q) DESC,"
    " name LIMIT :limit"
)


async def attribute_types(db: AsyncSession) -> dict[str, str]:
    rows = await db.execute(text("SELECT key, data_type FROM attribute_definitions"))
    return {row.key: row.data_type for row in rows}


async def upsert_attribute(
    db: AsyncSession,
    *,
    key: str,
    names: Mapping[str, str],
    data_type: str,
    enum_values: Sequence[tuple[str, Mapping[str, str]]] | None,
    unit: str | None,
    constraints: Mapping[str, int | float],
) -> UUID:
    row = await db.execute(
        _UPSERT_ATTRIBUTE,
        {
            "id": new_id(),
            "key": key,
            "names": json.dumps(names),
            "data_type": data_type,
            "enum_values": (
                json.dumps([{"key": k, "names": names} for k, names in enum_values])
                if enum_values
                else None
            ),
            "unit": unit,
            "constraints": json.dumps(constraints),
        },
    )
    return row.scalar_one()


async def upsert_category(db: AsyncSession, **values: Any) -> UUID:
    """Insert or update by key; `values` holds the columns of `_UPSERT_CATEGORY`."""
    params = values | {"id": new_id(), "names": json.dumps(values["names"])}
    return (await db.execute(_UPSERT_CATEGORY, params)).scalar_one()


async def deactivate_categories_except(db: AsyncSession, keys: Sequence[str]) -> None:
    await db.execute(
        text("UPDATE categories SET is_active = false WHERE is_active AND NOT (key = ANY(:keys))"),
        {"keys": list(keys)},
    )


async def replace_category_attributes(
    db: AsyncSession, category_ids: Sequence[UUID], links: Sequence[Mapping[str, Any]]
) -> None:
    await db.execute(
        text("DELETE FROM category_attributes WHERE category_id = ANY(:ids)"),
        {"ids": list(category_ids)},
    )
    if links:
        await db.execute(_INSERT_CATEGORY_ATTRIBUTE, list(links))


async def insert_brands(db: AsyncSession, brands: Sequence[tuple[str, str]]) -> None:
    """(name, slug) pairs; a brand already there (by name or slug) is left as it is."""
    if brands:
        await db.execute(
            text(
                "INSERT INTO brands (id, name, slug) VALUES (:id, :name, :slug)"
                " ON CONFLICT DO NOTHING"
            ),
            [{"id": new_id(), "name": name, "slug": slug} for name, slug in brands],
        )


async def active_categories(db: AsyncSession, *, verticals: bool) -> Sequence[Row[Any]]:
    return (await db.execute(_ACTIVE_CATEGORIES, {"verticals": verticals})).all()


async def category_attributes(db: AsyncSession, ids: Sequence[UUID]) -> Sequence[Row[Any]]:
    return (await db.execute(_CATEGORY_ATTRIBUTES, {"ids": list(ids)})).all()


async def attributes(db: AsyncSession, keys: Sequence[str]) -> Sequence[Row[Any]]:
    return (await db.execute(_ATTRIBUTES, {"keys": list(keys)})).all()


async def search_brands(db: AsyncSession, *, prefix: str, q: str, limit: int) -> Sequence[Row[Any]]:
    return (await db.execute(_SEARCH_BRANDS, {"prefix": prefix, "q": q, "limit": limit})).all()
