"""Where a new listing stands (P2-T03b2a, section 8.11, plan P2 Q20): the real position of the
seller's address or zone, a public position 200 to 500 m away drawn once per source and shared
by all its listings, drawn again only when the source moves; H3 cells of the real position."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

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


async def test_one_public_position_per_source(sessionmaker: Session) -> None:
    """Twenty listings at one address show one point: their average says nothing more."""
    seller = await make_account(sessionmaker, completed=True)
    address = await make_address(sessionmaker, seller.id)
    zone = await make_zone(sessionmaker, seller.id)
    publics: set[tuple[float, float]] = set()
    for _ in range(20):
        location = await _locate(sessionmaker, seller.id, "address", address)
        assert location is not None
        publics.add((location.public_lat, location.public_lon))
    assert len(publics) == 1
    other = await _locate(sessionmaker, seller.id, "zone", zone)
    assert other is not None
    assert (other.public_lat, other.public_lon) not in publics


async def test_drawn_again_when_the_source_moves(sessionmaker: Session) -> None:
    seller = await make_account(sessionmaker, completed=True)
    address = await make_address(sessionmaker, seller.id)
    before = await _locate(sessionmaker, seller.id, "address", address)
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE addresses SET location = ST_MakePoint(2.35, 48.85)::geography"
                " WHERE id = :id"
            ),
            {"id": address},
        )
        await db.commit()
    after = await _locate(sessionmaker, seller.id, "address", address)
    assert before is not None and after is not None
    assert (after.lat, after.lon) == (48.85, 2.35)
    assert (
        200
        <= await _meters(sessionmaker, (48.85, 2.35), (after.public_lat, after.public_lon))
        <= 500
    )
    again = await _locate(sessionmaker, seller.id, "address", address)
    assert again is not None
    assert (again.public_lat, again.public_lon) == (after.public_lat, after.public_lon)


async def test_concurrent_listings_share_the_draw(sessionmaker: Session) -> None:
    seller = await make_account(sessionmaker, completed=True)
    zone = await make_zone(sessionmaker, seller.id)
    locations = await asyncio.gather(
        *(_locate(sessionmaker, seller.id, "zone", zone) for _ in range(8))
    )
    assert len({(loc.public_lat, loc.public_lon) for loc in locations if loc}) == 1
    assert all(locations)


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
    assert export["listing_public_positions"] == [
        {"location_source": "zone", "location_source_id": zone, "drawn_at": NOW}
    ]
    assert left == [other.id]
