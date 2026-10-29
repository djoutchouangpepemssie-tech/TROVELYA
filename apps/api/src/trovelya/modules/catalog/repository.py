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
# index serves both; the caller escapes LIKE wildcards in the prefix. A brand typed by a member
# is suggested only once an active (moderated) listing carries it (E19).
_SEARCH_BRANDS = text(
    "SELECT name::text AS name, slug FROM brands b"
    " WHERE (name::text ILIKE :prefix ESCAPE '\\' OR name::text % :q)"
    " AND (b.origin = 'seed' OR EXISTS ("
    " SELECT 1 FROM listings l WHERE l.brand_id = b.id AND l.status = 'active'))"
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

# Brands the member typed (E19).
_EXPORT_BRANDS = text(
    "SELECT name::text AS name, created_at FROM brands WHERE created_by = :user_id"
    " ORDER BY created_at, name"
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
            ("brands", _EXPORT_BRANDS),
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
    # Brands the member typed: gone when no listing carries them, else kept and unlinked.
    await db.execute(
        text(
            "DELETE FROM brands b WHERE b.created_by = :u"
            " AND NOT EXISTS (SELECT 1 FROM listings l WHERE l.brand_id = b.id)"
        ),
        params,
    )
    await db.execute(text("UPDATE brands SET created_by = NULL WHERE created_by = :u"), params)


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


# --- Drafts (P2-T03b2b1) ----------------------------------------------------------------------

# The category of a new listing: active along its whole chain of parents, a leaf when none of
# its children is active.
_LISTING_CATEGORY = text(
    "WITH RECURSIVE chain AS ("
    " SELECT id, parent_id, is_active FROM categories WHERE key = :key"
    " UNION ALL"
    " SELECT p.id, p.parent_id, p.is_active FROM categories p JOIN chain c ON p.id = c.parent_id"
    ")"
    " SELECT c.id, c.vertical, c.brand_policy, c.shipping_allowed, c.max_photos,"
    " c.allowed_conditions::text[] AS allowed_conditions,"
    " (SELECT bool_and(is_active) FROM chain) AS is_active,"
    " NOT EXISTS (SELECT 1 FROM categories ch WHERE ch.parent_id = c.id AND ch.is_active)"
    " AS is_leaf"
    " FROM categories c WHERE c.key = :key"
)
_ATTRIBUTE_RULES = text(
    "SELECT a.key, a.data_type, ca.is_required,"
    " (SELECT array_agg(v->>'key') FROM jsonb_array_elements(a.enum_values) v) AS enum_keys,"
    " a.constraints"
    " FROM category_attributes ca JOIN attribute_definitions a ON a.id = ca.attribute_id"
    " WHERE ca.category_id = :category_id ORDER BY ca.position, a.key"
)
# A brand is found by name (citext) or by slug ("Saint Laurent" and "Saint-Laurent" are one).
_FIND_BRAND = text(
    "SELECT id FROM brands WHERE name = :name OR slug = :slug ORDER BY name = :name DESC LIMIT 1"
)
_CREATE_BRAND = text(
    "INSERT INTO brands (id, name, slug, origin, created_by)"
    " VALUES (:id, :name, :slug, 'member', :member_id) ON CONFLICT DO NOTHING"
)
_INSERT_LISTING = text(
    "INSERT INTO listings (id, short_id, seller_id, title, description, category_id, brand_id,"
    " condition, attributes, price_minor, currency, accepts_offers, handover_enabled,"
    " shipping_enabled, parcel_size, weight_g, location, location_public, h3_r7, h3_r9,"
    " place_name, country_code, location_source, location_source_id, created_at, updated_at)"
    " VALUES (:id, :short_id, :seller_id, :title, :description, :category_id, :brand_id,"
    " CAST(:condition AS item_condition), CAST(:attributes AS jsonb), :price_minor, :currency,"
    " :accepts_offers, :handover_enabled, :shipping_enabled, :parcel_size, :weight_g,"
    " ST_MakePoint(:lon, :lat)::geography, ST_MakePoint(:public_lon, :public_lat)::geography,"
    " :h3_r7, :h3_r9, :place_name, :country_code, :location_source, :location_source_id, :now,"
    " :now)"
    " ON CONFLICT (short_id) DO NOTHING RETURNING id"
)


async def listing_category(db: AsyncSession, key: str) -> Row[Any] | None:
    return (await db.execute(_LISTING_CATEGORY, {"key": key})).one_or_none()


async def attribute_rules(db: AsyncSession, category_id: UUID) -> Sequence[Row[Any]]:
    return (await db.execute(_ATTRIBUTE_RULES, {"category_id": category_id})).all()


async def brand_id(db: AsyncSession, *, name: str, slug: str, member_id: UUID) -> UUID:
    """The brand of that name or slug; created unverified, typed by the member, when there is
    none (Q3, E19)."""
    params = {"name": name, "slug": slug}
    found = await db.scalar(_FIND_BRAND, params)
    if found is None:
        await db.execute(_CREATE_BRAND, {**params, "id": new_id(), "member_id": member_id})
        found = await db.scalar(_FIND_BRAND, params)
    if found is None:  # inserted or found by a concurrent writer: never neither
        raise RuntimeError("brand neither found nor created")
    return found


async def insert_listing(db: AsyncSession, values: Mapping[str, Any]) -> bool:
    """False when the short id is already taken (draw another)."""
    params = {**values, "attributes": json.dumps(values["attributes"])}
    return (await db.execute(_INSERT_LISTING, params)).one_or_none() is not None


async def attach_photos(db: AsyncSession, listing_id: UUID, media_ids: Sequence[UUID]) -> None:
    """Raises IntegrityError when a photo is already in another listing."""
    await db.execute(
        text(
            "INSERT INTO listing_media (listing_id, media_id, position)"
            " SELECT :listing_id, m, p - 1"
            " FROM unnest(CAST(:ids AS uuid[])) WITH ORDINALITY u(m, p)"
        ),
        {"listing_id": listing_id, "ids": list(media_ids)},
    )


async def record_price(db: AsyncSession, listing_id: UUID, price_minor: int, now: datetime) -> None:
    await db.execute(
        text(
            "INSERT INTO listing_price_history (listing_id, price_minor, changed_at)"
            " VALUES (:listing_id, :price_minor, :now)"
        ),
        {"listing_id": listing_id, "price_minor": price_minor, "now": now},
    )


_OWN_LISTING = text(
    "SELECT l.id, l.short_id, l.status::text AS status, l.version, l.title, l.description,"
    " c.key AS category, b.name::text AS brand, l.condition::text AS condition, l.attributes,"
    " l.price_minor, l.currency, l.accepts_offers, l.handover_enabled, l.shipping_enabled,"
    " l.parcel_size, l.weight_g, l.place_name, l.country_code, l.location_source,"
    " l.location_source_id,"
    " (SELECT coalesce(array_agg(m.media_id ORDER BY m.position), '{}')"
    " FROM listing_media m WHERE m.listing_id = l.id) AS media_ids,"
    " l.created_at, l.updated_at"
    " FROM listings l JOIN categories c ON c.id = l.category_id"
    " LEFT JOIN brands b ON b.id = l.brand_id"
    " WHERE l.id = :id AND l.seller_id = :seller_id AND l.deleted_at IS NULL"
)


async def own_listing(
    db: AsyncSession, *, listing_id: UUID, seller_id: UUID
) -> dict[str, Any] | None:
    params = {"id": listing_id, "seller_id": seller_id}
    row = (await db.execute(_OWN_LISTING, params)).mappings().one_or_none()
    return dict(row) if row is not None else None


# --- Edits of drafts (P2-T03b2c) --------------------------------------------------------------

_LOCK_OWN_LISTING = text(
    "SELECT status::text AS status, version, price_minor, brand_id FROM listings"
    " WHERE id = :id AND seller_id = :seller_id AND deleted_at IS NULL FOR UPDATE"
)
# The position changes only when the seller picks another address or zone (`:locate`).
_UPDATE_LISTING = text(
    "UPDATE listings SET title = :title, description = :description,"
    " category_id = :category_id, brand_id = :brand_id,"
    " condition = CAST(:condition AS item_condition), attributes = CAST(:attributes AS jsonb),"
    " price_minor = :price_minor, currency = :currency, accepts_offers = :accepts_offers,"
    " handover_enabled = :handover_enabled, shipping_enabled = :shipping_enabled,"
    " parcel_size = :parcel_size, weight_g = :weight_g,"
    " location = CASE WHEN :locate THEN ST_MakePoint(:lon, :lat)::geography ELSE location END,"
    " location_public = CASE WHEN :locate"
    " THEN ST_MakePoint(:public_lon, :public_lat)::geography ELSE location_public END,"
    " h3_r7 = CASE WHEN :locate THEN :h3_r7 ELSE h3_r7 END,"
    " h3_r9 = CASE WHEN :locate THEN :h3_r9 ELSE h3_r9 END,"
    " place_name = CASE WHEN :locate THEN :place_name ELSE place_name END,"
    " country_code = CASE WHEN :locate THEN :country_code ELSE country_code END,"
    " location_source = CASE WHEN :locate THEN :location_source ELSE location_source END,"
    " location_source_id = CASE WHEN :locate"
    " THEN CAST(:location_source_id AS uuid) ELSE location_source_id END"
    " WHERE id = :id"
)


async def lock_own_listing(
    db: AsyncSession, *, listing_id: UUID, seller_id: UUID
) -> Row[Any] | None:
    params = {"id": listing_id, "seller_id": seller_id}
    return (await db.execute(_LOCK_OWN_LISTING, params)).one_or_none()


async def update_listing(db: AsyncSession, listing_id: UUID, values: Mapping[str, Any]) -> None:
    """The content of a locked listing; its version moves only if the content changed."""
    params = {**values, "id": listing_id, "attributes": json.dumps(values["attributes"])}
    await db.execute(_UPDATE_LISTING, params)


async def detach_photos(db: AsyncSession, listing_id: UUID) -> None:
    await db.execute(
        text("DELETE FROM listing_media WHERE listing_id = :listing_id"),
        {"listing_id": listing_id},
    )


async def lock_seller_listings(db: AsyncSession, seller_id: UUID) -> None:
    """One write of a seller's listings at a time: photos are taken in a single order, so two
    drafts never deadlock over them. Taken first, before any other lock."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('trovelya.listings:' || :s, 0))"),
        {"s": str(seller_id)},
    )


async def photos_in_other_listings(
    db: AsyncSession, listing_id: UUID, media_ids: Sequence[UUID]
) -> bool:
    return bool(
        await db.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM listing_media"
                " WHERE media_id = ANY(:ids) AND listing_id <> :listing_id)"
            ),
            {"ids": list(media_ids), "listing_id": listing_id},
        )
    )


async def bump_version_if(db: AsyncSession, listing_id: UUID, *, unchanged_from: int) -> None:
    """One more version when the content's triggers did not move it already."""
    await db.execute(
        text(
            "UPDATE listings SET version = version + 1, updated_at = now()"
            " WHERE id = :id AND version = :version"
        ),
        {"id": listing_id, "version": unchanged_from},
    )


async def drop_member_brand_if_unused(db: AsyncSession, *, brand_id: UUID, member_id: UUID) -> None:
    """A brand the member typed and no listing carries any more (E19)."""
    await db.execute(
        text(
            "DELETE FROM brands b WHERE b.id = :id AND b.origin = 'member'"
            " AND b.created_by = :member"
            " AND NOT EXISTS (SELECT 1 FROM listings l WHERE l.brand_id = b.id)"
        ),
        {"id": brand_id, "member": member_id},
    )


# --- Reading a listing (P2-T03b3a) -----------------------------------------------------------

# Never a coordinate out: the distance to the viewer is computed here on the public position.
_LISTING_PAGE = text(
    "SELECT l.id, l.short_id, l.seller_id, l.status::text AS status, l.title, l.description,"
    " c.id AS category_id, c.key AS category_key, c.names->>'fr' AS category_name,"
    " b.name::text AS brand, l.condition::text AS condition, l.attributes, l.price_minor,"
    " l.currency, l.accepts_offers, l.handover_enabled, l.shipping_enabled, l.parcel_size,"
    " l.weight_g,"
    " l.place_name, l.published_at, l.updated_at,"
    " (SELECT coalesce(array_agg(m.media_id ORDER BY m.position), '{}')"
    " FROM listing_media m WHERE m.listing_id = l.id) AS media_ids,"
    " CASE WHEN CAST(:viewer_lat AS double precision) IS NULL THEN NULL"
    " ELSE ST_Distance(l.location_public,"
    " ST_MakePoint(:viewer_lon, :viewer_lat)::geography) END AS distance_m"
    " FROM listings l JOIN categories c ON c.id = l.category_id"
    " LEFT JOIN brands b ON b.id = l.brand_id"
    " WHERE l.id = :id AND l.deleted_at IS NULL"
)


async def listing_page(
    db: AsyncSession, listing_id: UUID, viewer: tuple[float, float] | None
) -> dict[str, Any] | None:
    params = {
        "id": listing_id,
        "viewer_lat": viewer[0] if viewer else None,
        "viewer_lon": viewer[1] if viewer else None,
    }
    row = (await db.execute(_LISTING_PAGE, params)).mappings().one_or_none()
    return dict(row) if row is not None else None
