"""Rules a draft follows before anything is written (P2-T03b2b1, section 7.5, plan P2 Q3).

Its category must be an active leaf (real estate, vehicles and services only with the
`verticals` flag); its condition one the category accepts; shipping only where the category
allows it; its brand as the category's policy says (an unknown brand is created unverified for the
member, E19);
its attributes checked against the category's (all errors at once); at most the category's
number of photos.
"""

import hashlib
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode, FieldError
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.models import ItemCondition
from trovelya.modules.catalog.service.attributes import AttributeRule, validate_attributes
from trovelya.modules.catalog.service.brand_seed import slugify
from trovelya.shared.clock import Clock

# The year of attributes is the French one: on 1 January at 00:30 in Paris, it is the new year.
LOCAL_ZONE = ZoneInfo("Europe/Paris")

_ATTRIBUTE_MESSAGES = {
    "required": "Caractéristique obligatoire",
    "unknown": "Caractéristique inconnue dans cette catégorie",
    "type": "Type de valeur incorrect",
    "not_in_list": "Valeur hors de la liste proposée",
    "too_small": "Valeur trop petite",
    "too_large": "Valeur trop grande",
    "step": "Valeur hors du pas autorisé",
    "too_long": "Texte trop long",
    "empty": "Texte vide",
    "invalid_characters": "Caractères non autorisés",
}


def _invalid(code: ErrorCode) -> AppError:
    return AppError(code, 422)


async def checked_attributes(
    db: AsyncSession, category_id: UUID, values: dict[str, Any], clock: Clock
) -> dict[str, Any]:
    rules = [
        AttributeRule(
            key=row.key,
            data_type=row.data_type,
            is_required=row.is_required,
            enum_keys=frozenset(row.enum_keys) if row.enum_keys is not None else None,
            constraints=row.constraints,
        )
        for row in await repository.attribute_rules(db, category_id)
    ]
    year = clock.now().astimezone(LOCAL_ZONE).year
    accepted, issues = validate_attributes(values, rules, current_year=year)
    if issues:
        raise AppError(
            ErrorCode.INVALID_ATTRIBUTES,
            422,
            errors=[
                FieldError(field=f"attributes.{key}", code=code, message=_ATTRIBUTE_MESSAGES[code])
                for key, code in issues
            ],
        )
    return accepted


def brand_slug(name: str) -> str | None:
    """The latin slug of the name; for a name in another alphabet (Greek, Cyrillic…), a stable
    `b-` slug from its case-folded form; None without any letter or digit."""
    if not any(c.isalnum() for c in name):
        return None
    slug = slugify(name)
    if slug:
        return slug
    return "b-" + hashlib.sha256(name.casefold().encode()).hexdigest()[:16]


async def brand_for(
    db: AsyncSession, policy: str, name: str | None, *, member_id: UUID
) -> UUID | None:
    """The brand the category's policy calls for; an unknown one is created for the member."""
    if name is None:
        if policy == "required":
            raise _invalid(ErrorCode.BRAND_REQUIRED)
        return None
    if policy == "none":
        raise _invalid(ErrorCode.BRAND_NOT_ALLOWED)
    slug = brand_slug(name)
    if slug is None:
        raise _invalid(ErrorCode.BRAND_INVALID)
    return await repository.brand_id(db, name=name, slug=slug, member_id=member_id)


async def checked_category(
    db: AsyncSession,
    *,
    key: str,
    condition: ItemCondition,
    shipping: bool,
    photos: int,
    verticals: bool,
) -> Row[Any]:
    """The draft's category, once its rules are met; 422 with the rule broken otherwise."""
    category = await repository.listing_category(db, key)
    if category is None:
        raise _invalid(ErrorCode.CATEGORY_UNKNOWN)
    if not category.is_active or (category.vertical != "goods" and not verticals):
        raise _invalid(ErrorCode.CATEGORY_INACTIVE)
    if not category.is_leaf:
        raise _invalid(ErrorCode.CATEGORY_NOT_LEAF)
    if category.allowed_conditions and condition not in category.allowed_conditions:
        raise _invalid(ErrorCode.CONDITION_NOT_ALLOWED)
    if shipping and not category.shipping_allowed:
        raise _invalid(ErrorCode.SHIPPING_NOT_ALLOWED)
    if photos > category.max_photos:
        raise _invalid(ErrorCode.MEDIA_LIMIT)
    return category
