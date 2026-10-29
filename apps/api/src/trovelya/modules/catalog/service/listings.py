"""Drafts of listings (section 11.5 `POST /v1/listings`, P2-T03b2b2).

A draft follows its category's rules (`draft_rules`) before anything is written; its photos
are the seller's own, processed listing photos; its position comes from one of the seller's
addresses or zones. It gets a random short id (E10) and its first price in the history.
"""

import secrets
import string
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.schemas import ListingDraftIn, ListingOut
from trovelya.modules.catalog.service import draft_rules
from trovelya.modules.catalog.service.locations import listing_location
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

SHORT_ID_ALPHABET = string.digits + string.ascii_letters
SHORT_ID_LENGTH = 10
SHORT_ID_ATTEMPTS = 3


def _short_id() -> str:
    return "".join(secrets.choice(SHORT_ID_ALPHABET) for _ in range(SHORT_ID_LENGTH))


async def create_draft(
    db: AsyncSession, *, seller_id: UUID, body: ListingDraftIn, verticals: bool, clock: Clock
) -> ListingOut:
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
    now = clock.now()
    location = await listing_location(
        db, seller_id=seller_id, source=body.location.source, source_id=body.location.id, now=now
    )
    if location is None:
        raise AppError(ErrorCode.LOCATION_UNAVAILABLE, 422)
    values = {
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
        "now": now,
    }
    listing_id = new_id()
    for _ in range(SHORT_ID_ATTEMPTS):
        if await repository.insert_listing(
            db, {**values, "id": listing_id, "short_id": _short_id()}
        ):
            break
    else:  # three collisions out of 62^10: the alphabet or the generator is broken
        raise RuntimeError("no free short id")
    try:
        async with db.begin_nested():
            await repository.attach_photos(db, listing_id, body.media_ids)
    except IntegrityError as exc:
        raise AppError(ErrorCode.MEDIA_IN_USE, 409) from exc
    await repository.record_price(db, listing_id, body.price.amount_minor, now)
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
