"""Test-only catalog route: mounted when ENV is "local" or "test", never elsewhere.

`POST /v1/_test/listing-in-review` creates a seller and their listing awaiting moderation (a
photo as the worker leaves it, the reason `weapons`), so the end-to-end tests of the staff's
queue need neither the upload nor the worker. The catalog is seeded first when empty.
Nothing here exists on staging or in production.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from trovelya.core.db import Uow
from trovelya.modules.catalog.service.listings import _short_id  # pyright: ignore[reportPrivateUsage]
from trovelya.modules.catalog.service.moderation import label
from trovelya.modules.catalog.service.seed import load_seed
from trovelya.modules.catalog.service.seed_writer import apply_seed
from trovelya.modules.catalog.service.states import Actor, apply_transition
from trovelya.modules.catalog.state_machine import ListingEvent
from trovelya.modules.identity.service import get_clock
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

router = APIRouter(prefix="/v1/_test", tags=["test"], include_in_schema=False)

TITLE = "Pistolet ancien de collection"
_SELLER = text(
    "INSERT INTO users (id, email, username, display_name, birth_year, profile_completed_at)"
    " VALUES (:id, :email, :username, 'Vendeur', 1985, now())"
)
_PHOTO = text(
    "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes, status,"
    " sha256, exif_stripped, variants, moderation) VALUES (:id, :owner, 'image', 'listing',"
    " :key, 'image/jpeg', 1000, 'ready', :sha, true, CAST(:variants AS jsonb), '{}')"
)
_LISTING = text(
    "INSERT INTO listings (id, short_id, seller_id, title, description, category_id, condition,"
    " price_minor, location, location_public, h3_r7, h3_r9, place_name, country_code,"
    " location_source, location_source_id)"
    " SELECT :id, :short_id, :seller, :title, :description, c.id, 'good', 12000,"
    " ST_MakePoint(2.35, 48.85)::geography, ST_MakePoint(2.35, 48.85)::geography,"
    " 608533320520982527, 617540519050084351, 'Paris', 'FR', 'zone', :zone"
    " FROM categories c WHERE c.key = 'mode.femme.robes'"
)


class ListingInReview(BaseModel):
    id: str
    seller_id: str
    title: str


@router.post("/listing-in-review", operation_id="test_listing_in_review")
async def test_listing_in_review(
    db: Uow, clock: Annotated[Clock, Depends(get_clock)]
) -> ListingInReview:
    if await db.scalar(text("SELECT count(*) FROM categories")) == 0:
        await apply_seed(db, load_seed())
    seller, media, listing = new_id(), new_id(), new_id()
    names = {"id": seller, "email": f"e2e-seller-{seller.hex}@example.org"}
    await db.execute(_SELLER, names | {"username": f"v_{seller.hex[-12:]}"})
    variants = f'[{{"format": "webp", "width": 640, "height": 480, "key": "{new_id().hex}"}}]'
    await db.execute(
        _PHOTO,
        {
            "id": media,
            "owner": seller,
            "key": new_id().hex,
            "sha": b"\x01" * 32,
            "variants": variants,
        },
    )
    await db.execute(
        _LISTING,
        {
            "id": listing,
            "short_id": _short_id(),
            "seller": seller,
            "title": TITLE,
            "description": "Belle patine, mécanisme complet, vendu en l'état.",
            "zone": new_id(),
        },
    )
    await db.execute(
        text("INSERT INTO listing_media (listing_id, media_id, position) VALUES (:l, :m, 0)"),
        {"l": listing, "m": media},
    )
    await apply_transition(
        db,
        listing_id=listing,
        event=ListingEvent.SUBMIT_FOR_REVIEW,
        actor=Actor("user", seller),
        clock=clock,
        reason_code="weapons",
        reason_text=label("weapons"),
    )
    return ListingInReview(id=str(listing), seller_id=str(seller), title=TITLE)
