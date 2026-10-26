"""GDPR export and erasure of the catalog (P2-T03a1 and T03a2, registries of ADR-0016, plan
P2 Q13): a member's listings, favorites and price watches are exported; at erasure the listings
go, with what hangs on them, and so do the member's favorites and price watches."""

from collections.abc import AsyncIterator
from typing import Any
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
                " ST_GeogFromText('POINT(4.85 45.76)'), 1, 2, 'Lyon 7e', 'FR', 'zone', :source)"
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
        await db.execute(
            text("INSERT INTO listing_price_history (listing_id, price_minor) VALUES (:l, 2500)"),
            {"l": listing_id},
        )
        await db.execute(
            text(
                "INSERT INTO listing_status_history (id, listing_id, to_status, event, actor_id,"
                " actor_kind) VALUES (:h, :l, 'draft', 'create', :seller, 'user')"
            ),
            {"h": new_id(), "l": listing_id, "seller": seller},
        )
        await db.commit()
    return listing_id


async def _execute(sessionmaker: Session, sql: str, **params: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def test_catalog_exported(sessionmaker: Session, category: UUID) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    own = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    others = await _listing(sessionmaker, other.id, category, "Vase de Biot bleu")
    await _execute(
        sessionmaker,
        "INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)",
        u=member.id,
        l=others,
    )
    await _execute(
        sessionmaker,
        "INSERT INTO price_watches (user_id, listing_id, target_minor) VALUES (:u, :l, 2000)",
        u=member.id,
        l=others,
    )
    async with sessionmaker() as db:
        export = await registered_exporters()["catalog"](db, member.id)

    [listing] = export["listings"]
    assert (listing["id"], listing["title"], listing["place_name"]) == (
        own,
        "Lampe opaline verte",
        "Lyon 7e",
    )
    assert (listing["latitude"], listing["longitude"]) == (45.75, 4.84)
    assert [entry["price_minor"] for entry in listing["price_history"]] == [2500]
    assert [(e["to_status"], e["event"]) for e in listing["status_history"]] == [
        ("draft", "create")
    ]
    # Internal or other people's data never leaves: no embedding, cells, staff identities.
    assert not {"embedding", "search_document", "h3_r7", "h3_r9", "location_public"} & set(listing)
    assert "actor_id" not in listing["status_history"][0]
    assert [f["listing_id"] for f in export["favorites"]] == [others]
    assert [(w["listing_id"], w["target_minor"]) for w in export["price_watches"]] == [
        (others, 2000)
    ]


async def test_catalog_erased(sessionmaker: Session, category: UUID) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    own = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    others = await _listing(sessionmaker, other.id, category, "Vase de Biot bleu")
    for sql in (
        "INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)",
        "INSERT INTO price_watches (user_id, listing_id) VALUES (:u, :l)",
    ):
        await _execute(sessionmaker, sql, u=member.id, l=others)
        await _execute(sessionmaker, sql, u=other.id, l=own)
    async with sessionmaker() as db:
        await registered_erasers()["catalog"](db, member.id)
        await db.commit()
        remaining = {
            table: await db.scalar(
                text(
                    f"SELECT count(*) FROM {table} WHERE user_id IN (:a, :b)"  # noqa: S608
                ),
                {"a": member.id, "b": other.id},
            )
            for table in ("favorites", "price_watches")
        }
        listings = set(
            (
                await db.scalars(
                    text("SELECT id FROM listings WHERE id IN (:a, :b)"),
                    {"a": own, "b": others},
                )
            ).all()
        )
    # The member's listings are gone (with the other member's favorite on them); the other
    # member's listing stays, without the erased member's favorite.
    assert listings == {others}
    assert remaining == {"favorites": 0, "price_watches": 0}
