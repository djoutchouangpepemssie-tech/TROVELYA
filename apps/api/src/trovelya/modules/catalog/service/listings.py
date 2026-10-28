"""Drafts of listings (section 11.5 `POST /v1/listings`, P2-T03b2b2).

A draft follows its category's rules (`draft_rules`) before anything is written; its photos
are the seller's own, processed listing photos; its position comes from one of the seller's
addresses or zones. It gets a random short id (E10) and its first price in the history.
"""

import secrets
import string
from typing import Any
from uuid import UUID

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.schemas import ListingDraftIn, ListingDraftPatch, ListingOut
from trovelya.modules.catalog.service import draft_rules
from trovelya.modules.catalog.service.locations import listing_location
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

SHORT_ID_ALPHABET = string.digits + string.ascii_letters
SHORT_ID_LENGTH = 10
SHORT_ID_ATTEMPTS = 3


_LOCATION_COLUMNS = (
    "lat",
    "lon",
    "public_lat",
    "public_lon",
    "h3_r7",
    "h3_r9",
    "place_name",
    "country_code",
    "location_source",
    "location_source_id",
)


def _short_id() -> str:
    return "".join(secrets.choice(SHORT_ID_ALPHABET) for _ in range(SHORT_ID_LENGTH))


async def _checked_values(
    db: AsyncSession,
    *,
    seller_id: UUID,
    body: ListingDraftIn,
    verticals: bool,
    clock: Clock,
    locate: bool,
) -> dict[str, Any]:
    """The columns of the draft once every rule is met; its position only when `locate`."""
    category = await draft_rules.checked_category(
        db,
        key=body.category,
        condition=body.condition,
        shipping=body.shipping_enabled,
        photos=len(body.media_ids),
        verticals=verticals,
    )
    attributes = await draft_rules.checked_attributes(db, category.id, body.attributes, clock)
    await listing_photos.check_listing_photos(db, owner_id=seller_id, media_ids=body.media_ids)
    values: dict[str, Any] = {
        "seller_id": seller_id,
        "title": body.title,
        "description": body.description,
        "category_id": category.id,
        "brand_id": await draft_rules.brand_for(
            db, category.brand_policy, body.brand, member_id=seller_id
        ),
        "condition": body.condition.value,
        "attributes": attributes,
        "price_minor": body.price.amount_minor,
        "currency": body.price.currency,
        "accepts_offers": body.accepts_offers,
        "handover_enabled": body.handover_enabled,
        "shipping_enabled": body.shipping_enabled,
        "parcel_size": body.parcel_size,
        "weight_g": body.weight_g,
        "now": clock.now(),
        "locate": locate,
    }
    if not locate:  # the position stays (the update's CASE keeps the columns)
        return values | dict.fromkeys(_LOCATION_COLUMNS)
    location = await listing_location(
        db,
        seller_id=seller_id,
        source=body.location.source,
        source_id=body.location.id,
        now=values["now"],
    )
    if location is None:
        raise AppError(ErrorCode.LOCATION_UNAVAILABLE, 422)
    return values | {
        "lat": location.lat,
        "lon": location.lon,
        "public_lat": location.public_lat,
        "public_lon": location.public_lon,
        "h3_r7": location.h3_r7,
        "h3_r9": location.h3_r9,
        "place_name": location.place_name,
        "country_code": location.country_code,
        "location_source": location.source,
        "location_source_id": location.source_id,
    }


async def _attach(db: AsyncSession, listing_id: UUID, media_ids: list[UUID]) -> None:
    try:
        async with db.begin_nested():
            await repository.attach_photos(db, listing_id, media_ids)
    except IntegrityError as exc:
        raise AppError(ErrorCode.MEDIA_IN_USE, 409) from exc


async def create_draft(
    db: AsyncSession, *, seller_id: UUID, body: ListingDraftIn, verticals: bool, clock: Clock
) -> ListingOut:
    values = await _checked_values(
        db, seller_id=seller_id, body=body, verticals=verticals, clock=clock, locate=True
    )
    now = values["now"]
    listing_id = new_id()
    for _ in range(SHORT_ID_ATTEMPTS):
        if await repository.insert_listing(
            db, {**values, "id": listing_id, "short_id": _short_id()}
        ):
            break
    else:  # three collisions out of 62^10: the alphabet or the generator is broken
        raise RuntimeError("no free short id")
    await _attach(db, listing_id, body.media_ids)
    await repository.record_price(db, listing_id, body.price.amount_minor, now)
    return await own_listing(db, seller_id=seller_id, listing_id=listing_id)


async def update_draft(
    db: AsyncSession,
    *,
    seller_id: UUID,
    listing_id: UUID,
    version: int,
    patch: ListingDraftPatch,
    verticals: bool,
    clock: Clock,
) -> ListingOut:
    """The draft with the fields sent changed, checked as a whole by the creation's rules.
    404 for anyone else's; 409 once it is no longer a draft (P2-T04 and P2-T05 decide how a
    published listing changes); 412 when `version` is stale."""
    locked = await repository.lock_own_listing(db, listing_id=listing_id, seller_id=seller_id)
    if locked is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if locked.status != "draft":
        raise AppError(ErrorCode.LISTING_NOT_EDITABLE, 409)
    if locked.version != version:
        raise AppError(ErrorCode.PRECONDITION_FAILED, 412)
    current = await own_listing(db, seller_id=seller_id, listing_id=listing_id)
    changes = patch.model_dump(exclude_unset=True)
    try:
        body = ListingDraftIn.model_validate(
            current.model_dump(include=set(ListingDraftIn.model_fields)) | changes
        )
    except ValidationError as exc:  # a field emptied that a draft needs
        raise RequestValidationError(exc.errors()) from exc
    values = await _checked_values(
        db,
        seller_id=seller_id,
        body=body,
        verticals=verticals,
        clock=clock,
        locate="location" in changes,
    )
    await repository.update_listing(db, listing_id, values)
    if body.media_ids != current.media_ids:
        await repository.detach_photos(db, listing_id)
        await _attach(db, listing_id, body.media_ids)
    if body.price.amount_minor != locked.price_minor:
        await repository.record_price(db, listing_id, body.price.amount_minor, values["now"])
    return await own_listing(db, seller_id=seller_id, listing_id=listing_id)


async def own_listing(db: AsyncSession, *, seller_id: UUID, listing_id: UUID) -> ListingOut:
    """The seller's listing; 404 for anyone else's (or a deleted one)."""
    row = await repository.own_listing(db, listing_id=listing_id, seller_id=seller_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return ListingOut.model_validate(
        row
        | {
            "price": {"amount_minor": row["price_minor"], "currency": row["currency"]},
            "location": {"source": row["location_source"], "id": row["location_source_id"]},
        }
    )
