"""Rules a draft follows (P2-T03b2b1), on the real seed: dresses (clothing size required),
smartphones (storage required), make-up (new and sealed items only), pianos (handover only), car
parts (a vertical); brands typed by members (Q3, E19); the seller's listing photos (E16)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.catalog.test_categories_api import (
    seeded,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.identity.test_profile import make_account
from trovelya.core.errors import AppError
from trovelya.modules.catalog.models import ItemCondition
from trovelya.modules.catalog.service import draft_rules
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]
# 23:30 UTC on 31 December is already the new year in Paris.
NEW_YEAR_IN_PARIS = FixedClock(datetime(2026, 12, 31, 23, 30, tzinfo=UTC))


@pytest.fixture
async def db(seeded: None, sessionmaker: Session) -> AsyncIterator[AsyncSession]:  # noqa: F811
    async with sessionmaker() as session:
        yield session
        await session.rollback()


async def photo(
    sessionmaker: Session, owner: UUID, *, purpose: str = "listing", status: str = "ready"
) -> UUID:
    """A photo as the media worker leaves it, classified clean (P2-T05b2)."""
    media_id = new_id()
    async with sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
                " status, sha256, exif_stripped, variants, rejection_reason, moderation)"
                " VALUES (:id, :owner, 'image', :purpose, :key, 'image/jpeg', 1000, :status,"
                " CASE WHEN :status = 'ready' THEN CAST(:sha AS bytea) END, :status = 'ready',"
                " CASE WHEN :status = 'ready' THEN CAST(:variants AS jsonb) ELSE '[]' END,"
                " CASE WHEN :status = 'rejected' THEN 'type_mismatch' END, CAST(:mod AS jsonb))"
            ),
            {
                "id": media_id,
                "owner": owner,
                "purpose": purpose,
                "key": new_id().hex,
                "status": status,
                "sha": b"\x01" * 32,
                "mod": '{"classification": {"by": "fake", "scores": {"nudity": 0, "violence": 0,'
                ' "weapons": 0, "drugs": 0}}}',
                "variants": f'[{{"format": "webp", "width": 640, "height": 480,'
                f' "key": "{new_id().hex}", "bytes": 20}}]',
            },
        )
        await session.commit()
    return media_id


async def _category(db: AsyncSession, key: str, **rules: Any) -> str:
    """The code of the rule broken, or "ok"."""
    values: dict[str, Any] = {
        "condition": ItemCondition.VERY_GOOD,
        "shipping": True,
        "photos": 1,
        "verticals": False,
    } | rules
    try:
        await draft_rules.checked_category(db, key=key, **values)
    except AppError as error:
        assert error.status == 422
        return error.code.value
    return "ok"


@pytest.mark.parametrize(
    ("key", "rules", "result"),
    [
        ("mode.femme.robes", {}, "ok"),
        ("mode.femme", {}, "category_not_leaf"),
        ("nulle.part", {}, "category_unknown"),
        ("vehicules.pieces.auto", {}, "category_inactive"),  # verticals flag off
        ("vehicules.pieces.auto", {"verticals": True}, "ok"),
        ("beaute_bien_etre.soins_maquillage.maquillage", {}, "condition_not_allowed"),
        (
            "beaute_bien_etre.soins_maquillage.maquillage",
            {"condition": ItemCondition.NEW_WITH_TAGS},
            "ok",
        ),
        ("culture_loisirs.instruments.pianos", {}, "shipping_not_allowed"),
        ("culture_loisirs.instruments.pianos", {"shipping": False}, "ok"),
        ("mode.femme.robes", {"photos": 12}, "ok"),
        ("mode.femme.robes", {"photos": 13}, "media_limit"),
    ],
)
async def test_category_rules(
    db: AsyncSession, key: str, rules: dict[str, Any], result: str
) -> None:
    assert await _category(db, key, **rules) == result


async def test_retired_category_refused(db: AsyncSession) -> None:
    await db.execute(text("UPDATE categories SET is_active = false WHERE key = 'mode.femme'"))
    assert await _category(db, "mode.femme.robes") == "category_inactive"  # its parent's gone


async def _attributes(db: AsyncSession, key: str, values: dict[str, Any]) -> Any:
    category = await draft_rules.checked_category(
        db,
        key=key,
        condition=ItemCondition.NEW_WITH_TAGS,
        shipping=False,
        photos=1,
        verticals=False,
    )
    try:
        return await draft_rules.checked_attributes(db, category.id, values, NEW_YEAR_IN_PARIS)
    except AppError as error:
        assert (error.status, error.code.value) == (422, "invalid_attributes")
        return sorted((e.field, e.code) for e in error.errors or [])


async def test_attributes_kept_in_the_category_order(db: AsyncSession) -> None:
    accepted = await _attributes(
        db, "mode.femme.robes", {"color": "bleu", "clothing_size": "m", "material": "lin"}
    )
    assert accepted == {"color": "bleu", "material": "lin", "clothing_size": "m"}


async def test_attributes_checked_all_at_once(db: AsyncSession) -> None:
    errors = await _attributes(db, "mode.femme.robes", {"color": "fuchsia", "storage_gb": "g128"})
    assert errors == [
        ("attributes.clothing_size", "required"),  # inherited from « Femme »
        ("attributes.color", "not_in_list"),
        ("attributes.storage_gb", "unknown"),  # an attribute of another category
    ]


async def test_required_attributes_of_a_leaf(db: AsyncSession) -> None:
    errors = await _attributes(db, "high_tech.telephones.smartphones", {})
    assert errors == [("attributes.storage_gb", "required")]
    sealed = await _attributes(db, "beaute_bien_etre.soins_maquillage.maquillage", {})
    assert sealed == [("attributes.sealed", "required")]


async def test_year_of_attributes_is_the_french_one(db: AsyncSession) -> None:
    """At 23:30 UTC on 31 December 2026, it is 2027 in Paris: 2028 models are accepted."""
    key = "culture_loisirs.livres_rares.livres_anciens"
    accepted = await _attributes(db, key, {"author": "Victor Hugo", "edition_year": 2028})
    assert accepted == {"author": "Victor Hugo", "edition_year": 2028}
    errors = await _attributes(db, key, {"author": "Victor Hugo", "edition_year": 2029})
    assert errors == [("attributes.edition_year", "too_large")]


@pytest.mark.parametrize(
    ("policy", "name", "result"),
    [
        ("required", None, "brand_required"),
        ("none", "Sézane", "brand_not_allowed"),
        ("optional", None, None),
        ("optional", "--- !", "brand_invalid"),  # neither a letter nor a digit
    ],
)
async def test_brand_policy(
    db: AsyncSession, sessionmaker: Session, policy: str, name: str | None, result: str | None
) -> None:
    member = await make_account(sessionmaker, completed=True)
    try:
        brand = await draft_rules.brand_for(db, policy, name, member_id=member.id)
    except AppError as error:
        assert (error.status, error.code.value) == (422, result)
        return
    assert result is None and brand is None


async def test_required_brand_of_smartphones_in_the_seed(db: AsyncSession) -> None:
    policy = await db.scalar(
        text("SELECT brand_policy FROM categories WHERE key = 'high_tech.telephones.smartphones'")
    )
    assert policy == "required"


async def test_member_brand_created_unverified_then_reused(
    db: AsyncSession, sessionmaker: Session
) -> None:
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    created = await draft_rules.brand_for(
        db, "optional", "Atelier Témoin Unique", member_id=member.id
    )
    again = await draft_rules.brand_for(
        db,
        "required",
        "atelier-temoin unique",
        member_id=other.id,  # same slug
    )
    assert created is not None and again == created
    row = (
        await db.execute(
            text("SELECT is_verified, origin, created_by FROM brands WHERE id = :id"),
            {"id": created},
        )
    ).one()
    assert (row.is_verified, row.origin, row.created_by) == (False, "member", member.id)  # Q3


@pytest.mark.parametrize("name", ["Ζάρα Ελλάς", "Българска марка", "日本ブランド"])
async def test_brands_in_any_alphabet(db: AsyncSession, sessionmaker: Session, name: str) -> None:
    """Free entry (Q3) in every EU alphabet: a slug is made even without a latin letter."""
    member = await make_account(sessionmaker, completed=True)
    brand = await draft_rules.brand_for(db, "optional", name, member_id=member.id)
    again = await draft_rules.brand_for(db, "optional", name.upper(), member_id=member.id)
    assert brand is not None and again == brand
    slug = await db.scalar(text("SELECT slug FROM brands WHERE id = :id"), {"id": brand})
    assert slug.startswith("b-")


async def test_seeded_brand_reused(db: AsyncSession, sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    row = (
        await db.execute(
            text("SELECT id, name::text AS name FROM brands WHERE origin = 'seed' LIMIT 1")
        )
    ).one()
    assert (
        await draft_rules.brand_for(db, "optional", row.name.upper(), member_id=member.id) == row.id
    )


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        ("others", 404, "not_found"),
        ("avatar", 422, "media_not_listing"),
        ("rejected", 422, "media_rejected"),
        ("processing", 409, "media_not_ready"),
        ("deleted", 404, "not_found"),
    ],
)
async def test_listing_photo_rules(
    db: AsyncSession, sessionmaker: Session, kind: str, status: int, code: str
) -> None:
    seller = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    good = await photo(sessionmaker, seller.id)
    bad = {
        "others": lambda: photo(sessionmaker, other.id),
        "avatar": lambda: photo(sessionmaker, seller.id, purpose="avatar"),
        "rejected": lambda: photo(sessionmaker, seller.id, status="rejected"),
        "processing": lambda: photo(sessionmaker, seller.id, status="processing"),
        "deleted": lambda: photo(sessionmaker, seller.id),
    }[kind]
    media = await bad()
    if kind == "deleted":
        await db.execute(text("UPDATE media SET deleted_at = now() WHERE id = :id"), {"id": media})
    await listing_photos.check_listing_photos(db, owner_id=seller.id, media_ids=[good])
    with pytest.raises(AppError) as raised:
        await listing_photos.check_listing_photos(db, owner_id=seller.id, media_ids=[good, media])
    assert (raised.value.status, raised.value.code.value) == (status, code)


async def test_checked_photos_locked_for_share(db: AsyncSession, sessionmaker: Session) -> None:
    """Until the listing's transaction ends, the purge cannot take the photo."""
    seller = await make_account(sessionmaker, completed=True)
    media = await photo(sessionmaker, seller.id)
    await listing_photos.check_listing_photos(db, owner_id=seller.id, media_ids=[media])
    async with sessionmaker() as purge:
        locked = await purge.execute(
            text("SELECT id FROM media WHERE id = :id FOR NO KEY UPDATE SKIP LOCKED"),
            {"id": media},
        )
        assert locked.all() == []
