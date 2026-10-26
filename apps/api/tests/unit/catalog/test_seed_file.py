"""The category seed file: validation and inheritance (P2-T01b, P2 plan review point 1)."""

import math
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from trovelya.modules.catalog.service.seed import (
    EnumValue,
    SeedError,
    load_seed,
    parse_seed,
    parse_yaml,
    read_seed_file,
)
from trovelya.modules.catalog.universes import UNIVERSE_KEYS


def _root(key: str, **overrides: Any) -> dict[str, Any]:
    node = {
        "key": key,
        "fr": key.capitalize(),
        "vertical": "goods",
        "model": "protected_purchase",
        "shipping": True,
        "max_photos": 12,
        "brand": "optional",
        "children": [{"key": f"{key}.divers", "fr": "Divers"}],
    }
    return node | overrides


def _document(**overrides: Any) -> dict[str, Any]:
    """A minimal valid seed: the 16 universes, one leaf each, one attribute."""
    document: dict[str, Any] = {
        "version": 1,
        "attributes": {
            "color": {"fr": "Couleur", "type": "enum", "values": {"noir": "Noir"}},
            "isbn": {"fr": "ISBN", "type": "text", "max_length": 17},
        },
        "categories": [_root(key) for key in UNIVERSE_KEYS],
    }
    return document | overrides


def _error(document: dict[str, Any]) -> str:
    with pytest.raises(SeedError) as error:
        parse_seed(document)
    return str(error.value)


def test_real_seed_file_is_valid() -> None:
    seed = load_seed()
    assert [c.key for c in seed.categories if c.parent_key is None] == list(UNIVERSE_KEYS)
    assert len(seed.categories) == 430
    assert sum(c.is_leaf for c in seed.categories) == 334
    assert len(seed.attributes) == 63


def test_seed_roots_equal_universe_keys() -> None:
    document = _document()
    document["categories"] = document["categories"][:-1]  # « autres » missing
    assert "racines" in _error(document)
    document = _document()
    document["categories"].append(_root("voitures"))
    assert "racines" in _error(document)


def test_inherited_attributes_resolved() -> None:
    seed = load_seed()
    dresses = seed.category("mode.femme.robes")
    assert [(a.key, a.is_required, a.is_filterable) for a in dresses.attributes] == [
        ("color", False, True),
        ("material", False, True),
        ("clothing_size", True, True),
    ]
    expected = ("goods", "protected_purchase", True)
    assert (dresses.vertical, dresses.transaction_model, dresses.shipping_allowed) == expected


def test_settings_overridden_below() -> None:
    seed = load_seed()
    assert seed.category("maison_jardin.meubles.canapes_fauteuils").shipping_allowed is False
    parts = seed.category("vehicules.pieces.auto")
    expected = ("protected_purchase", True, 12)
    assert (parts.transaction_model, parts.shipping_allowed, parts.max_photos) == expected
    assert seed.category("vehicules.voitures").max_photos == 30
    assert seed.category("collection.militaria.insignes").is_restricted is True
    cosmetics = seed.category("beaute_bien_etre.soins_maquillage.maquillage")
    assert cosmetics.allowed_conditions == ("new_with_tags", "new_without_tags")


def test_attributes_replace_starts_afresh() -> None:
    seed = load_seed()
    assert seed.category("sport_plein_air.velos.pieces").attributes == ()


def test_not_filterable_marker() -> None:
    novels = load_seed().category("culture_loisirs.livres.romans")
    isbn = next(a for a in novels.attributes if a.key == "isbn")
    assert (isbn.is_required, isbn.is_filterable) == (False, False)


def test_enum_values_and_constraints() -> None:
    seed = load_seed()
    color = seed.attribute("color")
    assert color.enum_values is not None
    assert EnumValue("bleu_marine", {"fr": "Bleu marine"}) in color.enum_values
    size = seed.attribute("clothing_size")
    assert size.enum_values is not None
    assert [v.key for v in size.enum_values][:4] == ["xxs", "xs", "s", "m"]  # file order
    assert seed.attribute("shoe_eu").constraints == {"min": 15, "max": 52, "step": 0.5}
    era = seed.attribute("era")
    assert era.enum_values is not None and "1900_1940" in [v.key for v in era.enum_values]


def test_positions_follow_file_order() -> None:
    seed = load_seed()
    assert [c.position for c in seed.categories if c.parent_key is None] == list(range(16))


Change = Callable[[dict[str, Any]], object]
_INVALID: list[tuple[Change, str]] = [
    (
        lambda d: d["categories"][0]["children"].append({"key": "mode.divers", "fr": "X"}),
        "doublon",
    ),
    (lambda d: d["categories"][0].update(vertical="cars"), "vertical"),
    (lambda d: d["categories"][0].update(model="auction"), "model"),
    (lambda d: d["categories"][0].update(brand="sometimes"), "brand"),
    (lambda d: d["categories"][0].update(max_photos=0), "max_photos"),
    (lambda d: d["categories"][0].update(conditions=["like_new"]), "conditions"),
    (lambda d: d["categories"][0].update(attributes=["size"]), "attribut inconnu"),
    (lambda d: d["categories"][0].update(colour="noir"), "champ inconnu"),
    (lambda d: d["categories"][0].pop("vertical"), "vertical"),
    (lambda d: d["categories"][0].update(children=[]), "feuille"),
    (lambda d: d["categories"][0]["children"][0].update(key="mode.Robes"), "clé"),
    (lambda d: d["categories"][0]["children"][0].update(key="maison.divers"), "parent"),
    (lambda d: d["categories"][0]["children"][0].pop("fr"), "fr"),
    (lambda d: d.update(version=2), "version"),
    (lambda d: d["attributes"].update(size={"fr": "Taille", "type": "enum"}), "values"),
    (
        lambda d: d["attributes"].update(size={"fr": "T", "type": "text", "values": {"a": "A"}}),
        "values",
    ),
    (lambda d: d["attributes"].update(size={"fr": "Taille", "type": "date"}), "type"),
    (lambda d: d["attributes"].update(Size={"fr": "Taille", "type": "text"}), "clé"),
    (lambda d: d["attributes"]["color"].update(values={"noir": 3}), "values"),
    (lambda d: d["categories"][0].update(conditions=["good", "good"]), "conditions"),
    (lambda d: d["attributes"]["isbn"].update(max_length=3.5), "max_length invalide"),
    (lambda d: d["attributes"]["isbn"].update(max_length=0), "positifs"),
    (lambda d: d["attributes"]["isbn"].update(min=1), "ne convient pas"),
    (lambda d: d["attributes"]["color"].update(max=3), "ne convient pas"),
    (lambda d: d["attributes"].update(n={"fr": "N", "type": "int", "min": 1.5}), "invalide"),
    (lambda d: d["attributes"].update(n={"fr": "N", "type": "decimal", "min": math.inf}), "inval"),
    (
        lambda d: d["attributes"].update(n={"fr": "N", "type": "decimal", "min": 3, "max": 2}),
        "min supérieur",
    ),
    (lambda d: d["attributes"].update(n={"fr": "N", "type": "decimal", "step": 0}), "positifs"),
    (lambda d: d["categories"][0]["children"][0].update(active=False), "tous ses enfants"),
]


@pytest.mark.parametrize(("change", "expected"), _INVALID)
def test_invalid_documents_refused(change: Change, expected: str) -> None:
    document = _document()
    change(document)
    assert expected in _error(document)


def test_moved_category_keeps_its_key() -> None:
    document = _document()
    document["categories"][1]["children"].append(
        {"key": "mode.ancienne_feuille", "fr": "Déplacée", "moved": True}
    )
    seed = parse_seed(document)
    moved = seed.category("mode.ancienne_feuille")
    assert (moved.parent_key, moved.path) == ("montres_bijoux", "montres_bijoux.ancienne_feuille")


def test_retired_category_retires_its_subtree() -> None:
    document = _document()
    retired = {"key": "mode.retiree", "fr": "R", "active": False}
    retired["children"] = [{"key": "mode.retiree.feuille", "fr": "F"}]  # type: ignore[assignment]
    document["categories"][0]["children"].append(retired)
    seed = parse_seed(document)
    assert seed.category("mode.retiree").is_active is False
    assert seed.category("mode.retiree.feuille").is_active is False


def test_yaml_key_written_twice_refused() -> None:
    with pytest.raises(SeedError, match="deux fois"):
        parse_yaml("attributes:\n  color: {fr: A, type: bool}\n  color: {fr: B, type: bool}\n")
    with pytest.raises(SeedError, match="deux fois"):
        parse_yaml("{key: a, fr: A, fr: B}")


def test_yaml_numbers_as_keys_refused() -> None:
    # « 1900_1940: … » without quotes is the integer 19001940 in YAML 1.1.
    document = _document()
    era = yaml.safe_load("{fr: Époque, type: enum, values: {1900_1940: x}}")
    document["attributes"]["era"] = era
    assert "values" in _error(document)


def test_read_seed_file_ships_with_the_package() -> None:
    assert read_seed_file("categories.yaml")["version"] == 1
