"""Writing the category seed (P2-T01b, P2 plan review point 1).

Each test works in a transaction that is rolled back, starting from the real seed.
"""

import copy
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from trovelya.modules.catalog.service.brand_seed import parse_brands
from trovelya.modules.catalog.service.seed import (
    SeedError,
    load_seed,
    parse_seed,
    read_seed_file,
)
from trovelya.modules.catalog.service.seed_writer import apply_brands, apply_seed
from trovelya.modules.catalog.universes import UNIVERSE_KEYS


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        await session.close()
        await transaction.rollback()


def _document() -> dict[str, Any]:
    return copy.deepcopy(read_seed_file("categories.yaml"))


def _node(document: dict[str, Any], key: str) -> dict[str, Any]:
    def walk(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
        for node in nodes:
            if node["key"] == key:
                return node
            if found := walk(node.get("children", [])):
                return found
        return None

    found = walk(document["categories"])
    assert found is not None
    return found


async def _snapshot(db: AsyncSession) -> dict[str, tuple[Any, ...]]:
    rows = await db.execute(
        text("SELECT key, id, path::text, names, is_active, position FROM categories")
    )
    return {row[0]: tuple(row[1:]) for row in rows}


async def _check_deferred(db: AsyncSession) -> None:
    """Run the commit-time checks now (the test transaction is never committed)."""
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_seed_writes_the_whole_tree(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    await _check_deferred(db)
    counts = (
        await db.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE parent_id IS NULL),"
                " (SELECT count(*) FROM attribute_definitions) FROM categories"
            )
        )
    ).one()
    assert tuple(counts) == (430, 16, 63)
    roots = await db.execute(
        text("SELECT key FROM categories WHERE parent_id IS NULL ORDER BY position")
    )
    assert tuple(r[0] for r in roots) == UNIVERSE_KEYS


async def _row_versions(db: AsyncSession) -> set[str]:
    """Physical row addresses: an UPDATE, even to the same values, moves the row."""
    rows = await db.execute(
        text(
            "SELECT 'c' || ctid::text FROM categories UNION ALL"
            " SELECT 'a' || ctid::text FROM attribute_definitions UNION ALL"
            " SELECT 'l' || ctid::text FROM category_attributes"
        )
    )
    return {row[0] for row in rows}


async def test_seed_idempotent_and_writes_nothing_when_unchanged(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    before, versions = await _snapshot(db), await _row_versions(db)
    await apply_seed(db, load_seed())
    await _check_deferred(db)
    assert await _snapshot(db) == before
    assert await _row_versions(db) == versions


async def test_category_settings_written(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    rows = await db.execute(
        text(
            "SELECT key, icon, vertical, transaction_model, shipping_allowed, max_photos,"
            " brand_policy, is_restricted, allowed_conditions::text[] FROM categories"
            " WHERE key = ANY(:keys) ORDER BY key"
        ),
        {
            "keys": [
                "beaute_bien_etre.soins_maquillage.maquillage",
                "collection.militaria.insignes",
                "immobilier.colocation",
                "maison_jardin.meubles.canapes_fauteuils",
                "mode",
                "vehicules.voitures",
            ]
        },
    )
    assert [tuple(r) for r in rows] == [
        (
            "beaute_bien_etre.soins_maquillage.maquillage",
            None,
            "goods",
            "protected_purchase",
            True,
            12,
            "required",
            False,
            ["new_with_tags", "new_without_tags"],
        ),
        (
            "collection.militaria.insignes",
            None,
            "goods",
            "protected_purchase",
            True,
            12,
            "none",
            True,
            None,
        ),
        ("immobilier.colocation", None, "real_estate", "contact", False, 30, "none", False, None),
        (
            "maison_jardin.meubles.canapes_fauteuils",
            None,
            "goods",
            "protected_purchase",
            False,
            12,
            "optional",
            False,
            None,
        ),
        ("mode", "mode", "goods", "protected_purchase", True, 12, "optional", False, None),
        ("vehicules.voitures", None, "vehicles", "mixed", False, 30, "required", False, None),
    ]


async def test_inherited_attributes_written_in_order(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    rows = await db.execute(
        text(
            "SELECT a.key, ca.is_required, ca.is_filterable, ca.position"
            " FROM category_attributes ca JOIN categories c ON c.id = ca.category_id"
            " JOIN attribute_definitions a ON a.id = ca.attribute_id"
            " WHERE c.key = 'mode.femme.robes' ORDER BY ca.position"
        )
    )
    assert [tuple(r) for r in rows] == [
        ("color", False, True, 0),
        ("material", False, True, 1),
        ("clothing_size", True, True, 2),
    ]


async def test_seed_rename_keeps_id(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    before = await _snapshot(db)
    document = _document()
    _node(document, "mode.femme.robes")["fr"] = "Robes et tuniques"
    await apply_seed(db, parse_seed(document))
    after = await _snapshot(db)
    assert after["mode.femme.robes"][0] == before["mode.femme.robes"][0]
    assert after["mode.femme.robes"][2] == {"fr": "Robes et tuniques"}


async def test_seed_move_recomputes_path(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    before = await _snapshot(db)
    document = _document()
    women = _node(document, "mode.femme")
    vintage = _node(document, "mode.vintage")
    moved = next(c for c in women["children"] if c["key"] == "mode.femme.combinaisons")
    women["children"].remove(moved)
    vintage["children"].append(moved | {"moved": True})
    await apply_seed(db, parse_seed(document))
    await _check_deferred(db)
    after = await _snapshot(db)
    assert after["mode.femme.combinaisons"][0] == before["mode.femme.combinaisons"][0]
    assert after["mode.femme.combinaisons"][1] == "mode.vintage.combinaisons"


async def test_seed_swap_of_two_paths(db: AsyncSession) -> None:
    """Two categories exchange their places in one load: their paths cross midway."""
    await apply_seed(db, load_seed())
    before = await _snapshot(db)
    document = _document()
    women, men = _node(document, "mode.femme"), _node(document, "mode.homme")
    women_shorts = next(c for c in women["children"] if c["key"] == "mode.femme.shorts")
    men_shorts = next(c for c in men["children"] if c["key"] == "mode.homme.shorts")
    women["children"][women["children"].index(women_shorts)] = men_shorts | {"moved": True}
    men["children"][men["children"].index(men_shorts)] = women_shorts | {"moved": True}
    await apply_seed(db, parse_seed(document))
    await _check_deferred(db)
    after = await _snapshot(db)
    assert after["mode.femme.shorts"][:2] == (before["mode.femme.shorts"][0], "mode.homme.shorts")
    assert after["mode.homme.shorts"][:2] == (before["mode.homme.shorts"][0], "mode.femme.shorts")


async def test_seed_removed_key_deactivated(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    document = _document()
    women = _node(document, "mode.femme")
    women["children"] = [c for c in women["children"] if c["key"] != "mode.femme.grossesse"]
    await apply_seed(db, parse_seed(document))
    await _check_deferred(db)
    row = (
        await db.execute(
            text("SELECT is_active, path::text FROM categories WHERE key = 'mode.femme.grossesse'")
        )
    ).one()
    assert tuple(row) == (False, "mode.femme.grossesse")
    # Back in the file: active again, same row.
    await apply_seed(db, load_seed())
    active = await db.execute(
        text("SELECT is_active FROM categories WHERE key = 'mode.femme.grossesse'")
    )
    assert active.scalar_one() is True


async def test_removed_category_follows_its_moved_parent(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    document = _document()
    women = _node(document, "mode.femme")
    women["children"] = [c for c in women["children"] if c["key"] != "mode.femme.grossesse"]
    culture = _node(document, "culture_loisirs")
    mode = _node(document, "mode")
    mode["children"].remove(women)
    culture["children"].append(women | {"moved": True})
    await apply_seed(db, parse_seed(document))
    await _check_deferred(db)
    path = await db.execute(
        text("SELECT path::text FROM categories WHERE key = 'mode.femme.grossesse'")
    )
    assert path.scalar_one() == "culture_loisirs.femme.grossesse"


async def test_attribute_type_change_refused(db: AsyncSession) -> None:
    await apply_seed(db, load_seed())
    document = _document()
    document["attributes"]["isbn"] = {"fr": "ISBN", "type": "int"}
    with pytest.raises(SeedError, match="type ne peut pas changer"):
        await apply_seed(db, parse_seed(document))


async def test_commit_time_violation_leaves_the_tree_as_it_was(db: AsyncSession) -> None:
    """A retired category still holds its path: a seed that wants it fails at commit, and
    rolling back keeps the previous tree (nothing half-written)."""
    await apply_seed(db, load_seed())
    await db.execute(
        text(
            "INSERT INTO categories (id, parent_id, key, path, names, is_active)"
            " SELECT gen_random_uuid(), id, 'ancienne.nouveautes', 'mode.femme.nouveautes',"
            " '{\"fr\":\"x\"}', false FROM categories WHERE key = 'mode.femme'"
        )
    )
    before = await _snapshot(db)
    document = _document()
    _node(document, "mode.femme")["children"].append(
        {"key": "mode.femme.nouveautes", "fr": "Nouveautés"}
    )
    savepoint = await db.begin_nested()
    await apply_seed(db, parse_seed(document))
    with pytest.raises(IntegrityError, match="categories_path_key"):
        await _check_deferred(db)
    await savepoint.rollback()
    assert await _snapshot(db) == before


async def test_brands_seeded_once_and_existing_kept(db: AsyncSession) -> None:
    await db.execute(
        text(
            "INSERT INTO brands (id, name, slug, is_verified)"
            " VALUES (gen_random_uuid(), 'marque graine', 'marque-graine', true)"
        )
    )
    brands = [("Marque Graine", "marque-graine"), ("Autre Graine", "autre-graine")]
    await apply_brands(db, brands)
    await apply_brands(db, brands)
    rows = await db.execute(
        text(
            "SELECT name::text, is_verified FROM brands"
            " WHERE slug IN ('marque-graine', 'autre-graine') ORDER BY slug"
        )
    )
    assert [tuple(r) for r in rows] == [("Autre Graine", False), ("marque graine", True)]


async def test_real_brands_file_loads(db: AsyncSession) -> None:
    brands = parse_brands(read_seed_file("brands.yaml"))
    await apply_brands(db, brands)
    found = await db.execute(
        text("SELECT count(*) FROM brands WHERE slug = ANY(:slugs)"),
        {"slugs": [slug for _, slug in brands]},
    )
    assert found.scalar_one() == len(brands)
