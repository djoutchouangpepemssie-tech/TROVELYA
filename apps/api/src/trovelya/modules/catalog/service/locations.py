"""Where a new or moved listing stands (section 8.11, plan P2 E13, E14 and Q20).

The seller picks one of their addresses or search zones; the listing takes its real position,
place name and country, the public position shared by every listing of that source, and the
H3 cells of the real position.

The offset is drawn once per place of the seller (Q20, E18): a source within `REUSE_M` of a
place already used by the seller takes that place's offset, so an address and a zone at home,
or a zone deleted and recreated, never scatter points around the home.
"""

from dataclasses import dataclass
from datetime import datetime
from random import Random
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.catalog import repository
from trovelya.modules.catalog.service.positions import (
    MAX_LATITUDE,
    SYSTEM_RANDOM,
    h3_cells,
    public_offset,
)
from trovelya.modules.identity.service import PlaceSource, member_place

# Farther than any re-typed or re-geocoded address; much less than the smallest offset (200 m).
REUSE_M = 50.0


@dataclass(frozen=True, slots=True)
class ListingLocation:
    source: PlaceSource
    source_id: UUID
    lat: float
    lon: float
    public_lat: float
    public_lon: float
    h3_r7: int
    h3_r9: int
    place_name: str
    country_code: str


async def listing_location(
    db: AsyncSession,
    *,
    seller_id: UUID,
    source: PlaceSource,
    source_id: UUID,
    now: datetime,
    rng: Random = SYSTEM_RANDOM,
) -> ListingLocation | None:
    """None when the source is not one of the seller's placed addresses or zones (or lies
    beyond 85 degrees, where no listing stands)."""
    place = await member_place(db, user_id=seller_id, source=source, source_id=source_id)
    if place is None or abs(place.lat) > MAX_LATITUDE:
        return None
    public_lat, public_lon = await repository.public_position(
        db,
        seller_id=seller_id,
        real=(place.lat, place.lon),
        drawn=public_offset(place.lat, place.lon, rng),
        reuse_m=REUSE_M,
        now=now,
    )
    h3_r7, h3_r9 = h3_cells(place.lat, place.lon)
    return ListingLocation(
        source=source,
        source_id=source_id,
        lat=place.lat,
        lon=place.lon,
        public_lat=public_lat,
        public_lon=public_lon,
        h3_r7=h3_r7,
        h3_r9=h3_r9,
        place_name=place.place_name,
        country_code=place.country_code,
    )
