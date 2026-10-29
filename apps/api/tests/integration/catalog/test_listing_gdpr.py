"""GDPR export and erasure of the catalog (P2-T03a1 and T03a2, registries of ADR-0016, plan
P2 Q13): a member's listings, favorites and price watches are exported; at erasure the listings
go, with what hangs on them, and so do the member's favorites and price watches."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
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


async def _photo(sessionmaker: Session, owner: UUID, listing: UUID, position: int) -> UUID:
    media_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
                " status) VALUES (:id, :owner, 'image', 'listing', :key, 'image/jpeg', 10,"
                " 'uploading')"
            ),
            {"id": media_id, "owner": owner, "key": new_id().hex},
        )
        await db.execute(
            text("INSERT INTO listing_media (listing_id, media_id, position) VALUES (:l, :m, :p)"),
            {"l": listing, "m": media_id, "p": position},
        )
        await db.commit()
    return media_id


async def test_catalog_exported(sessionmaker: Session, category: UUID) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    third = await make_account(sessionmaker, completed=True)
    own = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    others = await _listing(sessionmaker, other.id, category, "Vase de Biot bleu")
    second = await _photo(sessionmaker, member.id, own, 1)
    first = await _photo(sessionmaker, member.id, own, 0)
    for user in (member.id, third.id):  # the third member's must never be exported
        await _execute(
            sessionmaker,
            "INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)",
            u=user,
            l=others,
        )
        await _execute(
            sessionmaker,
            "INSERT INTO price_watches (user_id, listing_id, target_minor) VALUES (:u, :l, 2000)",
            u=user,
            l=others,
        )
    async with sessionmaker() as db:
        export = await registered_exporters()["catalog"](db, member.id, make_settings())

    [listing] = export["listings"]
    assert (listing["id"], listing["title"], listing["place_name"]) == (
        own,
        "Lampe opaline verte",
        "Lyon 7e",
    )
    assert (listing["latitude"], listing["longitude"]) == (45.75, 4.84)
    assert listing["category_name"] == "x"  # its French name, beside its key
    assert listing["category"].startswith("t_gdpr_")
    assert listing["media_ids"] == [str(first), str(second)]  # in display order
    assert [entry["price_minor"] for entry in listing["price_history"]] == [2500]
    assert [(e["to_status"], e["event"]) for e in listing["status_history"]] == [
        ("draft", "create")
    ]
    # Derived, internal or other people's data never leaves.
    assert not {"embedding", "search_document", "h3_r7", "h3_r9", "location_public"} & set(listing)
    assert "actor_id" not in listing["status_history"][0]
    assert [(f["listing_id"], f["title"]) for f in export["favorites"]] == [
        (others, "Vase de Biot bleu")
    ]
    assert [(w["listing_id"], w["target_minor"]) for w in export["price_watches"]] == [
        (others, 2000)
    ]


async def test_catalog_erased(sessionmaker: Session, category: UUID) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    third = await make_account(sessionmaker, completed=True)
    own = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    others = await _listing(sessionmaker, other.id, category, "Vase de Biot bleu")
    thirds = await _listing(sessionmaker, third.id, category, "Chaise Tolix rouge")
    photo = await _photo(sessionmaker, member.id, own, 0)
    for user, listing in ((member.id, others), (other.id, own), (other.id, thirds)):
        for sql in (
            "INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)",
            "INSERT INTO price_watches (user_id, listing_id) VALUES (:u, :l)",
        ):
            await _execute(sessionmaker, sql, u=user, l=listing)
    await _execute(
        sessionmaker,
        "UPDATE listings SET favorite_count = 1 WHERE id IN (:a, :b, :c)",
        a=own,
        b=others,
        c=thirds,
    )
    async with sessionmaker() as db:
        await registered_erasers()["catalog"](db, member.id)
        await db.commit()
        kept = {
            table: set(
                (
                    await db.execute(
                        text(
                            f"SELECT user_id, listing_id FROM {table}"  # noqa: S608
                            " WHERE user_id IN (:a, :b)"
                        ),
                        {"a": member.id, "b": other.id},
                    )
                ).all()
            )
            for table in ("favorites", "price_watches")
        }
        counts = dict(
            (
                await db.execute(
                    text("SELECT id, favorite_count FROM listings WHERE id IN (:a, :b, :c)"),
                    {"a": own, "b": others, "c": thirds},
                )
            ).all()
        )
        links = await db.scalar(
            text("SELECT count(*) FROM listing_media WHERE media_id = :m"), {"m": photo}
        )
    # The member's listing is gone with the other member's favorite and watch on it; the
    # member's own favorite and watch go too; nothing else is touched.
    assert counts == {others: 0, thirds: 1}
    assert kept == {
        "favorites": {(other.id, thirds)},
        "price_watches": {(other.id, thirds)},
    }
    assert links == 0
