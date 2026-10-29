"""Brands typed by members (Q3, E19): created unverified, never suggested to others until an
active listing carries them (a draft is not moderated), exported and erased with the member."""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.integration.catalog.test_categories_api import (
    catalog_client,
    seeded,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_listing_gdpr import _listing  # pyright: ignore[reportPrivateUsage]
from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers, registered_exporters
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]


@pytest.fixture
async def client(
    seeded: None,  # noqa: F811
    sessionmaker: Session,
    redis_client: Redis,
) -> AsyncIterator[AsyncClient]:
    async with await catalog_client(sessionmaker, redis_client, verticals=False) as c:
        yield c


async def _brand(sessionmaker: Session, member: UUID, name: str) -> UUID:
    """A brand as a member's draft creates it (P2-T03b2b1)."""
    brand = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO brands (id, name, slug, origin, created_by)"
                " VALUES (:id, :name, :slug, 'member', :member)"
            ),
            {"id": brand, "name": name, "slug": f"t-{brand.hex}", "member": member},
        )
        await db.commit()
    return brand


async def _suggested(client: AsyncClient, q: str) -> list[str]:
    response = await client.get("/v1/brands", params={"q": q})
    assert response.status_code == 200
    return [b["name"] for b in response.json()["brands"]]


async def _use(sessionmaker: Session, seller: UUID, brand: UUID, status: str) -> UUID:
    category = await _category(sessionmaker)
    listing = await _listing(sessionmaker, seller, category, "Montre ancienne dorée")
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE listings SET brand_id = :b, status = CAST(:s AS listing_status)"
                " WHERE id = :l"
            ),
            {"b": brand, "s": status, "l": listing},
        )
        await db.commit()
    return listing


async def _category(sessionmaker: Session) -> UUID:
    async with sessionmaker() as db:
        return await db.scalar(text("SELECT id FROM categories WHERE key = 'mode.femme.robes'"))


async def test_member_brand_hidden_until_an_active_listing(
    client: AsyncClient, sessionmaker: Session
) -> None:
    member = await make_account(sessionmaker, completed=True)
    brand = await _brand(sessionmaker, member.id, "Appelez Zéro Six Témoin")
    assert await _suggested(client, "Appelez Zéro") == []
    await _use(sessionmaker, member.id, brand, "draft")
    assert await _suggested(client, "Appelez Zéro") == []  # a draft is not moderated
    await _use(sessionmaker, member.id, brand, "active")
    assert await _suggested(client, "Appelez Zéro") == ["Appelez Zéro Six Témoin"]


async def test_seed_brands_still_suggested(client: AsyncClient, sessionmaker: Session) -> None:
    async with sessionmaker() as db:
        name = await db.scalar(text("SELECT name::text FROM brands WHERE origin = 'seed' LIMIT 1"))
    assert name in await _suggested(client, name)


async def test_member_brands_exported_and_erased(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    unused = await _brand(sessionmaker, member.id, "Atelier Effacé Témoin")
    shared = await _brand(sessionmaker, member.id, "Atelier Partagé Témoin")
    others = await _brand(sessionmaker, other.id, "Atelier Voisin Témoin")
    await _use(sessionmaker, other.id, shared, "active")  # another seller sells it
    async with sessionmaker() as db:
        export = await registered_exporters()["catalog"](db, member.id, make_settings())
        await registered_erasers()["catalog"](db, member.id)
        await db.commit()
        left = dict(
            (
                await db.execute(
                    text("SELECT id, created_by FROM brands WHERE id IN (:a, :b, :c)"),
                    {"a": unused, "b": shared, "c": others},
                )
            ).all()
        )
    assert sorted(b["name"] for b in export["brands"]) == [
        "Atelier Effacé Témoin",
        "Atelier Partagé Témoin",
    ]
    # The unused one is gone; the one another seller uses stays, linked to nobody.
    assert left == {shared: None, others: other.id}
