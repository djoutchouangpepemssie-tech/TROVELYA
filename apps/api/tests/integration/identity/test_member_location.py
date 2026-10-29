"""Where a member's listing stands (P2-T03b2a, section 8.11): the position of one of their
addresses or search zones and a place name that never holds the street; another member's,
a deleted or an unplaced address is not a position."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import make_account
from trovelya.modules.identity.service import MemberPlace, PlaceSource, member_place
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]


async def make_address(
    sessionmaker: Session,
    user_id: UUID,
    *,
    postal_code: str = "69100",
    city: str = "Villeurbanne",
    country_code: str = "FR",
    placed: bool = True,
    deleted: bool = False,
    at: tuple[float, float] = (45.77, 4.88),
) -> UUID:
    address_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO addresses (id, user_id, full_name, line1, postal_code, city,"
                " country_code, location, deleted_at)"
                " VALUES (:id, :u, 'Lucie Martin', '12 rue des Lilas', :pc, :city, :cc,"
                " CASE WHEN :placed THEN ST_MakePoint(:lon, :lat)::geography END,"
                " CASE WHEN :deleted THEN now() END)"
            ),
            {
                "id": address_id,
                "u": user_id,
                "pc": postal_code,
                "city": city,
                "cc": country_code,
                "placed": placed,
                "deleted": deleted,
                "lat": at[0],
                "lon": at[1],
            },
        )
        await db.commit()
    return address_id


async def make_zone(
    sessionmaker: Session,
    user_id: UUID,
    *,
    at: tuple[float, float] = (45.74, 4.84),
    place_name: str = "Lyon 7e",
    default: bool = False,
) -> UUID:
    zone_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO search_zones (id, user_id, label, place_name, center, radius_m,"
                " is_default)"
                " VALUES (:id, :u, 'Maison', :name, ST_MakePoint(:lon, :lat)::geography, 5000,"
                " :default)"
            ),
            {
                "id": zone_id,
                "u": user_id,
                "name": place_name,
                "lat": at[0],
                "lon": at[1],
                "default": default,
            },
        )
        await db.commit()
    return zone_id


async def _place(
    sessionmaker: Session, user_id: UUID, source: PlaceSource, source_id: UUID
) -> MemberPlace | None:
    async with sessionmaker() as db:
        return await member_place(db, user_id=user_id, source=source, source_id=source_id)


async def test_zone_position_and_name(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    zone = await make_zone(sessionmaker, member.id)
    assert await _place(sessionmaker, member.id, "zone", zone) == MemberPlace(
        lat=45.74, lon=4.84, place_name="Lyon 7e", country_code="FR"
    )


async def test_address_named_after_its_city(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    address = await make_address(sessionmaker, member.id)
    place = await _place(sessionmaker, member.id, "address", address)
    assert place == MemberPlace(lat=45.77, lon=4.88, place_name="Villeurbanne", country_code="FR")


@pytest.mark.parametrize(
    ("postal_code", "city", "name"),
    [
        ("75001", "Paris", "Paris 1er"),
        ("75007", "Paris", "Paris 7e"),
        ("75020", "Paris", "Paris 20e"),
        ("75116", "Paris", "Paris 16e"),
        ("69009", "Lyon", "Lyon 9e"),
        ("13016", "Marseille", "Marseille 16e"),
        ("69100", "Villeurbanne", "Villeurbanne"),
        ("13090", "Aix-en-Provence", "Aix-en-Provence"),
        ("75021", "Paris", "Paris"),  # not an arrondissement: the city
        ("75 008", "Paris", "Paris 8e"),  # typed with a space
        (" 69003 ", "Lyon", "Lyon 3e"),
        ("42000", "Saint-Étienne", "Saint-Étienne"),
        ("94240", "L'Haÿ-les-Roses", "L'Haÿ-les-Roses"),
        # A city that is not only a name never goes public: the postal code instead.
        ("69100", "Villeurbanne, 12 rue des Lilas", "69100"),
        ("69100", "12 rue des Lilas", "69100"),
    ],
)
async def test_arrondissement_from_the_postal_code(
    sessionmaker: Session, postal_code: str, city: str, name: str
) -> None:
    member = await make_account(sessionmaker, completed=True)
    address = await make_address(sessionmaker, member.id, postal_code=postal_code, city=city)
    place = await _place(sessionmaker, member.id, "address", address)
    assert place is not None
    assert place.place_name == name
    assert "rue des Lilas" not in place.place_name


async def test_foreign_address_keeps_its_city_and_country(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    address = await make_address(
        sessionmaker, member.id, postal_code="75007", city="Bruxelles", country_code="BE"
    )
    place = await _place(sessionmaker, member.id, "address", address)
    assert place is not None
    assert (place.place_name, place.country_code) == ("Bruxelles", "BE")


@pytest.mark.parametrize("name", ["Lyon 7e, 12 rue des Lilas", "12 rue des Lilas", "Lyon\n7e"])
async def test_zone_with_more_than_a_place_name_is_refused(
    sessionmaker: Session, name: str
) -> None:
    """A zone's name is sent by the client; one that is not a mere place name never goes
    public (section 8.11: never an exact address)."""
    member = await make_account(sessionmaker, completed=True)
    zone = await make_zone(sessionmaker, member.id, place_name=name)
    assert await _place(sessionmaker, member.id, "zone", zone) is None


async def test_no_position_without_a_placed_own_source(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    unplaced = await make_address(sessionmaker, member.id, placed=False)
    deleted = await make_address(sessionmaker, member.id, deleted=True)
    others_address = await make_address(sessionmaker, other.id)
    others_zone = await make_zone(sessionmaker, other.id)
    own_zone = await make_zone(sessionmaker, member.id)
    sources: list[tuple[PlaceSource, UUID]] = [
        ("address", unplaced),
        ("address", deleted),
        ("address", others_address),
        ("zone", others_zone),
        ("address", own_zone),  # a zone's id is not an address
        ("zone", new_id()),
    ]
    for source, source_id in sources:
        assert await _place(sessionmaker, member.id, source, source_id) is None
