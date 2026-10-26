"""GDPR export and erasure of the catalog (P2-T03a1, registries of ADR-0016, plan P2 Q13): a
member's listings are exported, and deleted at erasure."""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers, registered_exporters
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]


@pytest.fixture
async def category(sessionmaker: Session) -> AsyncIterator[UUID]:
    """A category of its own, removed afterwards with its listings: other tests count the
    categories of the seed."""
    category_id = new_id()
    key = f"t_gdpr_{category_id.hex[:12]}"
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO categories (id, key, path, names) VALUES (:id, :key,"
                ' text2ltree(:key), \'{"fr":"x"}\')'
            ),
            {"id": category_id, "key": key},
        )
        await db.commit()
    yield category_id
    async with sessionmaker() as db:
        await db.execute(text("DELETE FROM listings WHERE category_id = :c"), {"c": category_id})
        await db.execute(text("DELETE FROM categories WHERE id = :c"), {"c": category_id})
        await db.commit()


async def _listing(sessionmaker: Session, seller: UUID, category: UUID, title: str) -> UUID:
    listing_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO listings (id, short_id, seller_id, title, description, category_id,"
                " condition, price_minor, location, location_public, h3_r7, h3_r9, place_name,"
                " country_code, location_source, location_source_id)"
                " VALUES (:id, :short_id, :seller, :title, 'Une description assez longue.',"
                " :category, 'good', 2500, ST_GeogFromText('POINT(4.84 45.75)'),"
                " ST_GeogFromText('POINT(4.84 45.7527)'), 1, 2, 'Lyon 7e', 'FR', 'zone', :source)"
            ),
            {
                "id": listing_id,
                "short_id": listing_id.hex[-10:],
                "seller": seller,
                "title": title,
                "category": category,
                "source": new_id(),
            },
        )
        await db.commit()
    return listing_id


async def test_catalog_exported(sessionmaker: Session, category: UUID) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    own = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    await _listing(sessionmaker, other.id, category, "Vase de Biot bleu")
    async with sessionmaker() as db:
        export = await registered_exporters()["catalog"](db, member.id)

    [listing] = export["listings"]
    assert (listing["id"], listing["title"], listing["place_name"]) == (
        own,
        "Lampe opaline verte",
        "Lyon 7e",
    )
    assert (listing["latitude"], listing["longitude"]) == (45.75, 4.84)
    assert listing["category_name"] == "x"  # its French name, beside its key
    assert listing["category"].startswith("t_gdpr_")
    # Derived or internal data never leaves: no embedding, cells or public offset.
    assert not {"embedding", "search_document", "h3_r7", "h3_r9", "location_public"} & set(listing)


async def test_catalog_erased(sessionmaker: Session, category: UUID) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    own = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    others = await _listing(sessionmaker, other.id, category, "Vase de Biot bleu")
    async with sessionmaker() as db:
        await registered_erasers()["catalog"](db, member.id)
        await db.commit()
        listings = set(
            (
                await db.scalars(
                    text("SELECT id FROM listings WHERE id IN (:a, :b)"),
                    {"a": own, "b": others},
                )
            ).all()
        )
    assert listings == {others}
