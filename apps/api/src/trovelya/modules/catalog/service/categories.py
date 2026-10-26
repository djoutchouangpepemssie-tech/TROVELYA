"""Reading the category tree and brands (P2-T01b)."""

from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.catalog import repository
from trovelya.modules.catalog.schemas import (
    AttributeOut,
    AttributeValueOut,
    BrandList,
    BrandOut,
    CategoryAttributeOut,
    CategoryOut,
    CategoryTree,
)

LOCALE = "fr"  # the only language until the 24 languages arrive; `names` keeps them all
BRAND_SUGGESTIONS = 10


def _name(names: dict[str, Any]) -> str:
    return str(names[LOCALE])


async def category_tree(db: AsyncSession, *, verticals: bool) -> CategoryTree:
    """Active categories; real estate, vehicles and services only with the `verticals` flag."""
    rows = await repository.active_categories(db, verticals=verticals)
    links: dict[Any, list[CategoryAttributeOut]] = defaultdict(list)
    for link in await repository.category_attributes(db, [row.id for row in rows]):
        links[link.category_id].append(
            CategoryAttributeOut(
                key=link.key, required=link.is_required, filterable=link.is_filterable
            )
        )
    categories = [
        CategoryOut(
            key=row.key,
            parent_key=row.parent_key,  # always served before its children
            name=_name(row.names),
            icon=row.icon,
            position=row.position,
            is_leaf=row.is_leaf,
            vertical=row.vertical,
            transaction_model=row.transaction_model,
            shipping_allowed=row.shipping_allowed,
            max_photos=row.max_photos,
            is_restricted=row.is_restricted,
            brand_policy=row.brand_policy,
            allowed_conditions=row.allowed_conditions,
            attributes=links[row.id],
        )
        for row in rows
    ]
    used = sorted({a.key for c in categories for a in c.attributes})
    attributes = [
        AttributeOut(
            key=row.key,
            name=_name(row.names),
            type=row.data_type,
            unit=row.unit,
            values=(
                [AttributeValueOut(key=v["key"], name=_name(v["names"])) for v in row.enum_values]
                if row.enum_values
                else None
            ),
            **row.constraints,
        )
        for row in await repository.attributes(db, used)
    ]
    return CategoryTree(categories=categories, attributes=attributes)


def _like_prefix(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "%"


async def search_brands(db: AsyncSession, q: str) -> BrandList:
    rows = await repository.search_brands(db, prefix=_like_prefix(q), q=q, limit=BRAND_SUGGESTIONS)
    return BrandList(brands=[BrandOut(name=row.name, slug=row.slug) for row in rows])
