"""SQL of the catalog module. Only this module's service reads or writes these tables."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
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
    " WHERE (attribute_definitions.names, attribute_definitions.enum_values,"
    " attribute_definitions.unit, attribute_definitions.constraints)"
    " IS DISTINCT FROM (EXCLUDED.names, EXCLUDED.enum_values, EXCLUDED.unit, EXCLUDED.constraints)"
    " RETURNING id"
)

_UPSERT_CATEGORY = text(
    "INSERT INTO categories AS c (id, parent_id, key, path, names, icon, position, is_active,"
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
    " WHERE (c.parent_id, c.path, c.names, c.icon, c.position, c.is_active, c.is_restricted,"
    " c.vertical, c.transaction_model, c.shipping_allowed, c.max_photos, c.allowed_conditions,"
    " c.brand_policy) IS DISTINCT FROM (EXCLUDED.parent_id, EXCLUDED.path, EXCLUDED.names,"
    " EXCLUDED.icon, EXCLUDED.position, EXCLUDED.is_active, EXCLUDED.is_restricted,"
    " EXCLUDED.vertical, EXCLUDED.transaction_model, EXCLUDED.shipping_allowed,"
    " EXCLUDED.max_photos, EXCLUDED.allowed_conditions, EXCLUDED.brand_policy)"
    " RETURNING id"
)

# Links of the seeded categories: those gone are deleted, the others inserted or updated only
# when they changed (a deployment that changes nothing writes nothing).
_DELETE_STALE_LINKS = text(
    "DELETE FROM category_attributes ca WHERE ca.category_id = ANY(:ids) AND NOT EXISTS ("
    " SELECT 1 FROM unnest(CAST(:categories AS uuid[]), CAST(:attributes AS uuid[])) d(c, a)"
    " WHERE d.c = ca.category_id AND d.a = ca.attribute_id)"
)
_UPSERT_LINKS = text(
    "INSERT INTO category_attributes AS ca (category_id, attribute_id, is_required,"
    " is_filterable, position)"
    " SELECT * FROM unnest(CAST(:categories AS uuid[]), CAST(:attributes AS uuid[]),"
    " CAST(:required AS boolean[]), CAST(:filterable AS boolean[]), CAST(:positions AS int2[]))"
    " ON CONFLICT (category_id, attribute_id) DO UPDATE SET is_required = EXCLUDED.is_required,"
    " is_filterable = EXCLUDED.is_filterable, position = EXCLUDED.position"
    " WHERE (ca.is_required, ca.is_filterable, ca.position)"
    " IS DISTINCT FROM (EXCLUDED.is_required, EXCLUDED.is_filterable, EXCLUDED.position)"
)


async def lock_seed(db: AsyncSession) -> None:
    """One seed load at a time (two deployments at once wait for each other)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('trovelya.catalog_seed'))"))


async def _id_by_key(db: AsyncSession, table: str, key: str) -> UUID:
    query = {
        "categories": "SELECT id FROM categories WHERE key = :key",
        "attribute_definitions": "SELECT id FROM attribute_definitions WHERE key = :key",
    }
    return (await db.execute(text(query[table]), {"key": key})).scalar_one()


# Active categories in tree order (parents first, siblings by position). The walk stops at a
# retired category, so its subtree is never served; without the `verticals` flag, whole
# universes of real estate, vehicles and services are left out. A category is a leaf when
# none of its children is active.
_ACTIVE_CATEGORIES = text(
    "WITH RECURSIVE ordered AS ("
    " SELECT id, ARRAY[position::int] AS sort FROM categories"
    " WHERE parent_id IS NULL AND is_active AND (CAST(:verticals AS boolean) OR vertical = 'goods')"
    " UNION ALL"
    " SELECT c.id, o.sort || c.position::int FROM categories c JOIN ordered o ON c.parent_id = o.id"
    " WHERE c.is_active"
    ")"
    " SELECT c.id, c.key, p.key AS parent_key, c.names, c.icon, c.position, c.vertical,"
    " c.transaction_model, c.shipping_allowed, c.max_photos, c.is_restricted, c.brand_policy,"
    " c.allowed_conditions::text[] AS allowed_conditions,"
    " NOT EXISTS (SELECT 1 FROM categories ch WHERE ch.parent_id = c.id AND ch.is_active)"
    " AS is_leaf"
    " FROM ordered o JOIN categories c ON c.id = o.id"
    " LEFT JOIN categories p ON p.id = c.parent_id"
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
    return row.scalar_one_or_none() or await _id_by_key(db, "attribute_definitions", key)


async def upsert_category(db: AsyncSession, **values: Any) -> UUID:
    """Insert or update by key; `values` holds the columns of `_UPSERT_CATEGORY`."""
    params = values | {"id": new_id(), "names": json.dumps(values["names"])}
    changed = (await db.execute(_UPSERT_CATEGORY, params)).scalar_one_or_none()
    return changed or await _id_by_key(db, "categories", values["key"])


async def deactivate_categories_except(db: AsyncSession, keys: Sequence[str]) -> None:
    await db.execute(
        text("UPDATE categories SET is_active = false WHERE is_active AND NOT (key = ANY(:keys))"),
        {"keys": list(keys)},
    )


async def sync_category_attributes(
    db: AsyncSession, category_ids: Sequence[UUID], links: Sequence[Mapping[str, Any]]
) -> None:
    columns = {
        "categories": [link["category_id"] for link in links],
        "attributes": [link["attribute_id"] for link in links],
    }
    await db.execute(_DELETE_STALE_LINKS, {"ids": list(category_ids)} | columns)
    if links:
        await db.execute(
            _UPSERT_LINKS,
            columns
            | {
                "required": [link["is_required"] for link in links],
                "filterable": [link["is_filterable"] for link in links],
                "positions": [link["position"] for link in links],
            },
        )


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


# GDPR export (ADR-0016): the member's listings, every column they provided or that describes
# them, with their photos, price and status histories (no staff identity); their favorites and
# price watches. Not exported, being derived or internal: the public position (an offset of the
# real one), H3 cells, embedding, search document, quality score, the id of the address or zone
# the position came from (the address itself is in the identity export), and the links of
# later phases (shop, product variant, passport, resale, boost).
_EXPORT_LISTINGS = text(
    "SELECT l.id, l.short_id, l.status::text AS status, l.title, l.description,"
    " c.key AS category, c.names->>'fr' AS category_name, b.name::text AS brand,"
    " l.condition::text AS condition, l.attributes,"
    " l.price_minor, l.currency, l.original_price_minor, l.quantity, l.accepts_offers,"
    " l.min_offer_minor, l.handover_enabled, l.shipping_enabled, l.parcel_size, l.weight_g,"
    " ST_Y(l.location::geometry) AS latitude, ST_X(l.location::geometry) AS longitude,"
    " l.place_name, l.country_code, l.location_source, l.sale_modes, l.open_to_swap,"
    " l.published_at, l.sold_at, l.expires_at, l.view_count, l.favorite_count,"
    " l.created_at, l.updated_at, l.deleted_at,"
    " (SELECT coalesce(jsonb_agg(m.media_id ORDER BY m.position), '[]')"
    " FROM listing_media m WHERE m.listing_id = l.id) AS media_ids,"
    " (SELECT coalesce(jsonb_agg(jsonb_build_object('price_minor', p.price_minor,"
    " 'changed_at', p.changed_at) ORDER BY p.changed_at, p.id), '[]')"
    " FROM listing_price_history p WHERE p.listing_id = l.id) AS price_history,"
    " (SELECT coalesce(jsonb_agg(jsonb_build_object('from_status', h.from_status,"
    " 'to_status', h.to_status, 'event', h.event, 'actor_kind', h.actor_kind,"
    " 'reason_code', h.reason_code, 'reason_text', h.reason_text, 'created_at', h.created_at)"
    " ORDER BY h.created_at, h.id), '[]')"
    " FROM listing_status_history h WHERE h.listing_id = l.id) AS status_history"
    " FROM listings l JOIN categories c ON c.id = l.category_id"
    " LEFT JOIN brands b ON b.id = l.brand_id"
    " WHERE l.seller_id = :user_id ORDER BY l.created_at"
)
# Another member's listing is named by its short id and title only.
_EXPORT_FAVORITES = text(
    "SELECT f.listing_id, l.short_id, l.title, f.created_at FROM favorites f"
    " JOIN listings l ON l.id = f.listing_id WHERE f.user_id = :user_id ORDER BY f.created_at"
)
_EXPORT_PRICE_WATCHES = text(
    "SELECT w.listing_id, l.short_id, l.title, w.target_minor, w.created_at FROM price_watches w"
    " JOIN listings l ON l.id = w.listing_id WHERE w.user_id = :user_id ORDER BY w.created_at"
)

# The member's places kept for public positions, with the date of the draw; not the public
# position itself (derived). The place is kept even once its address or zone is gone.
_EXPORT_PUBLIC_POSITIONS = text(
    "SELECT ST_Y(location::geometry) AS latitude, ST_X(location::geometry) AS longitude, drawn_at"
    " FROM listing_public_positions WHERE seller_id = :user_id ORDER BY drawn_at, id"
)


async def export_catalog(db: AsyncSession, user_id: UUID) -> dict[str, list[dict[str, Any]]]:
    params = {"user_id": user_id}
    return {
        name: [dict(row) for row in (await db.execute(query, params)).mappings()]
        for name, query in (
            ("listings", _EXPORT_LISTINGS),
            ("favorites", _EXPORT_FAVORITES),
            ("price_watches", _EXPORT_PRICE_WATCHES),
            ("listing_public_positions", _EXPORT_PUBLIC_POSITIONS),
        )
    }


async def erase_catalog(db: AsyncSession, user_id: UUID) -> None:
    """GDPR eraser (within the account's erasure, plan P2 Q13): the member's listings are
    deleted with what hangs on them (photo links, other members' favorites and watches,
    histories); the photos themselves go with the media eraser and purge. The member's own
    favorites and price watches on other listings go too, their favorite counts with them."""
    params = {"u": user_id}
    await db.execute(
        text(
            "WITH gone AS (DELETE FROM favorites WHERE user_id = :u RETURNING listing_id)"
            " UPDATE listings l SET favorite_count = greatest(l.favorite_count - 1, 0)"
            " FROM gone WHERE l.id = gone.listing_id"
        ),
        params,
    )
    await db.execute(text("DELETE FROM price_watches WHERE user_id = :u"), params)
    await db.execute(text("DELETE FROM listings WHERE seller_id = :u"), params)
    await db.execute(text("DELETE FROM listing_public_positions WHERE seller_id = :u"), params)


# Q20 and E18: one draw per place of the seller. Under the seller's lock, the nearest kept place
# within REUSE_M lends its offset; otherwise the new draw is kept.
_LOCK_SELLER_PLACES = text(
    "SELECT pg_advisory_xact_lock(hashtextextended('trovelya.public_position:' || :seller_id, 0))"
)
_NEAREST_PLACE = text(
    "SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,"
    " ST_Y(location_public::geometry) AS public_lat, ST_X(location_public::geometry) AS public_lon"
    " FROM listing_public_positions"
    " WHERE seller_id = :seller_id AND ST_DWithin(location, ST_MakePoint(:lon, :lat)::geography,"
    " :reuse_m)"
    " ORDER BY ST_Distance(location, ST_MakePoint(:lon, :lat)::geography), drawn_at, id LIMIT 1"
)
_KEEP_PLACE = text(
    "INSERT INTO listing_public_positions (id, seller_id, location, location_public, drawn_at)"
    " VALUES (:id, :seller_id, ST_MakePoint(:lon, :lat)::geography,"
    " ST_MakePoint(:public_lon, :public_lat)::geography, :now)"
)


async def public_position(
    db: AsyncSession,
    *,
    seller_id: UUID,
    real: tuple[float, float],
    drawn: tuple[float, float],
    reuse_m: float,
    now: datetime,
) -> tuple[float, float]:
    """The public position of `real`: the offset of the seller's nearest place within `reuse_m`
    applied to it, else `drawn`, then kept."""
    params = {"seller_id": str(seller_id), "lat": real[0], "lon": real[1], "reuse_m": reuse_m}
    await db.execute(_LOCK_SELLER_PLACES, params)
    near = (await db.execute(_NEAREST_PLACE, params)).one_or_none()
    if near is not None and (near.lat, near.lon) == real:
        return near.public_lat, near.public_lon  # the very place: the very point, bit for bit
    if near is not None:
        public_lon = real[1] + near.public_lon - near.lon
        return real[0] + near.public_lat - near.lat, (public_lon + 180.0) % 360.0 - 180.0
    await db.execute(
        _KEEP_PLACE,
        {
            **params,
            "id": new_id(),
            "seller_id": seller_id,
            "public_lat": drawn[0],
            "public_lon": drawn[1],
            "now": now,
        },
    )
    return drawn
