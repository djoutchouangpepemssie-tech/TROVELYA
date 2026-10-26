"""Where a new listing stands (P2-T03b2a, section 8.11, plan P2 Q20 and E18): the real position
of the seller's address or zone, a public position 200 to 500 m away drawn once per place of
the seller and shared by all its listings, whatever source they come from; H3 cells of the
real position."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_member_location import make_address, make_zone
from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers, registered_exporters
from trovelya.modules.catalog.service.locations import ListingLocation, listing_location
from trovelya.modules.catalog.service.positions import h3_cells
from trovelya.modules.identity.service import PlaceSource

Session = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 10, 26, 20, 0, tzinfo=UTC)


async def _locate(
    sessionmaker: Session, seller: UUID, source: PlaceSource, source_id: UUID
) -> ListingLocation | None:
    async with sessionmaker() as db:
        location = await listing_location(
            db, seller_id=seller, source=source, source_id=source_id, now=NOW
        )
        await db.commit()
    return location


async def _meters(sessionmaker: Session, a: tuple[float, float], b: tuple[float, float]) -> float:
    async with sessionmaker() as db:
        return float(
            await db.scalar(
                text(
                    "SELECT ST_Distance(ST_MakePoint(:alon, :alat)::geography,"
                    " ST_MakePoint(:blon, :blat)::geography)"
                ),
                {"alat": a[0], "alon": a[1], "blat": b[0], "blon": b[1]},
            )
        )


async def test_zone_location(sessionmaker: Session) -> None:
    seller = await make_account(sessionmaker, completed=True)
    zone = await make_zone(sessionmaker, seller.id)
    location = await _locate(sessionmaker, seller.id, "zone", zone)
    assert location is not None
    assert (location.lat, location.lon, location.place_name, location.country_code) == (
        45.74,
        4.84,
        "Lyon 7e",
        "FR",
    )
    assert (location.source, location.source_id) == ("zone", zone)
    assert (location.h3_r7, location.h3_r9) == h3_cells(45.74, 4.84)
    public = (location.public_lat, location.public_lon)
    assert 200 <= await _meters(sessionmaker, (45.74, 4.84), public) <= 500


async def _public(sessionmaker: Session, seller: UUID, source: PlaceSource, source_id: UUID):
    location = await _locate(sessionmaker, seller, source, source_id)
    assert location is not None
    return location


async def _draws(sessionmaker: Session, seller: UUID) -> int:
    async with sessionmaker() as db:
        return int(
            await db.scalar(
                text("SELECT count(*) FROM listing_public_positions WHERE seller_id = :s"),
                {"s": seller},
            )
        )


async def test_one_public_position_per_place(sessionmaker: Session) -> None:
    """Listings of one place show one point, from any address or zone there: their average
    says nothing more (Q20)."""
    seller = await make_account(sessionmaker, completed=True)
    address = await make_address(sessionmaker, seller.id, at=(45.74, 4.84))
    zone = await make_zone(sessionmaker, seller.id, at=(45.74, 4.84))
    publics = {
        (loc.public_lat, loc.public_lon)
        for loc in [await _public(sessionmaker, seller.id, "address", address) for _ in range(10)]
        + [await _public(sessionmaker, seller.id, "zone", zone) for _ in range(10)]
    }
    assert len(publics) == 1
    assert await _draws(sessionmaker, seller.id) == 1


async def test_nearby_source_moves_the_same_offset(sessionmaker: Session) -> None:
    """A few meters away (a re-typed address, a recreated zone): the same offset, moved with
    the real position; no new draw."""
    seller = await make_account(sessionmaker, completed=True)
    first = await _public(sessionmaker, seller.id, "zone", await make_zone(sessionmaker, seller.id))
    near = await _public(
        sessionmaker,
        seller.id,
        "address",
        await make_address(sessionmaker, seller.id, at=(45.7401, 4.84)),  # 11 m north
    )
    assert near.public_lat - near.lat == pytest.approx(first.public_lat - first.lat, abs=1e-9)
    assert near.public_lon - near.lon == pytest.approx(first.public_lon - first.lon, abs=1e-9)
    assert await _draws(sessionmaker, seller.id) == 1


async def test_another_place_another_draw_and_back(sessionmaker: Session) -> None:
    seller = await make_account(sessionmaker, completed=True)
    address = await make_address(sessionmaker, seller.id)
    lyon = await _public(sessionmaker, seller.id, "address", address)
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE addresses SET location = ST_MakePoint(2.35, 48.85)::geography"
                " WHERE id = :id"
            ),
            {"id": address},
        )
        await db.commit()
    paris = await _public(sessionmaker, seller.id, "address", address)
    assert (paris.lat, paris.lon) == (48.85, 2.35)
    distance = await _meters(sessionmaker, (48.85, 2.35), (paris.public_lat, paris.public_lon))
    assert 200 <= distance <= 500
    # Back in Lyon, from a new zone: Lyon's draw again, never a second one around it.
    back = await _public(
        sessionmaker, seller.id, "zone", await make_zone(sessionmaker, seller.id, at=(45.77, 4.88))
    )
    assert (back.public_lat, back.public_lon) == (lyon.public_lat, lyon.public_lon)
    assert await _draws(sessionmaker, seller.id) == 2


async def test_other_sellers_never_share_a_draw(sessionmaker: Session) -> None:
    seller = await make_account(sessionmaker, completed=True)
    neighbour = await make_account(sessionmaker, completed=True)
    mine = await _public(sessionmaker, seller.id, "zone", await make_zone(sessionmaker, seller.id))
    theirs = await _public(
        sessionmaker, neighbour.id, "zone", await make_zone(sessionmaker, neighbour.id)
    )
    assert (mine.public_lat, mine.public_lon) != (theirs.public_lat, theirs.public_lon)


async def test_concurrent_listings_share_the_draw(sessionmaker: Session) -> None:
    """Eight listings at once, from sources a few meters apart: one draw (the seller's lock)."""
    seller = await make_account(sessionmaker, completed=True)
    zones = [
        await make_zone(sessionmaker, seller.id, at=(45.74 + i * 0.00001, 4.84)) for i in range(8)
    ]
    locations = await asyncio.gather(
        *(_locate(sessionmaker, seller.id, "zone", zone) for zone in zones)
    )
    offsets = {
        (round(loc.public_lat - loc.lat, 9), round(loc.public_lon - loc.lon, 9))
        for loc in locations
        if loc
    }
    assert all(locations)
    assert len(offsets) == 1
    assert await _draws(sessionmaker, seller.id) == 1


async def test_no_location_from_another_members_source(sessionmaker: Session) -> None:
    seller = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    zone = await make_zone(sessionmaker, other.id)
    unplaced = await make_address(sessionmaker, seller.id, placed=False)
    assert await _locate(sessionmaker, seller.id, "zone", zone) is None
    assert await _locate(sessionmaker, seller.id, "address", unplaced) is None
    async with sessionmaker() as db:
        drawn = await db.scalar(
            text("SELECT count(*) FROM listing_public_positions WHERE seller_id = :s"),
            {"s": seller.id},
        )
    assert drawn == 0


async def test_draws_exported_without_positions_and_erased(sessionmaker: Session) -> None:
    seller = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    zone = await make_zone(sessionmaker, seller.id)
    others_zone = await make_zone(sessionmaker, other.id)
    await _locate(sessionmaker, seller.id, "zone", zone)
    await _locate(sessionmaker, other.id, "zone", others_zone)
    async with sessionmaker() as db:
        export = await registered_exporters()["catalog"](db, seller.id)
        await registered_erasers()["catalog"](db, seller.id)
        await db.commit()
        left = (
            (
                await db.execute(
                    text(
                        "SELECT seller_id FROM listing_public_positions WHERE seller_id IN (:a, :b)"
                    ),
                    {"a": seller.id, "b": other.id},
                )
            )
            .scalars()
            .all()
        )
    # The real place is the member's own data, kept here even once the zone is gone.
    assert export["listing_public_positions"] == [
        {"latitude": 45.74, "longitude": 4.84, "drawn_at": NOW}
    ]
    assert left == [other.id]
