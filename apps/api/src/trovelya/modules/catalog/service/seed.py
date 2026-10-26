"""Category seed: read and validate `seed/categories.yaml` and `seed/brands.yaml` (P2-T01b).

The file is the source of truth of the tree (P2 plan, Q2). It is validated entirely before
anything is written (`seed_writer`). Settings and attributes are inherited down the tree as
the file's header explains; this module resolves the inheritance once, so every category
carries its complete list of attributes.
"""

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any, cast, get_args

import yaml

from trovelya.modules.catalog.models import (
    AttributeType,
    BrandPolicy,
    ItemCondition,
    TransactionModel,
    Vertical,
)
from trovelya.modules.catalog.universes import UNIVERSE_KEYS

SEED_VERSION = 1
_KEY = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
_ATTRIBUTE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_VALUE_KEY = re.compile(r"^[a-z0-9_]+$")
_INHERITED = ("vertical", "model", "shipping", "max_photos", "brand", "restricted", "conditions")
_ROOT_REQUIRED = ("vertical", "model", "shipping", "max_photos", "brand")
_OWN_FIELDS = ("key", "fr", "icon", "attributes", "attributes_replace", "children", "active")
_NODE_FIELDS = frozenset((*_INHERITED, *_OWN_FIELDS, "moved"))
_ATTRIBUTE_FIELDS = frozenset({"fr", "type", "values", "unit", "min", "max", "step", "max_length"})
_CONSTRAINTS = ("min", "max", "step", "max_length")


class SeedError(ValueError):
    """The seed file breaks a rule; nothing is written."""


@dataclass(frozen=True, slots=True)
class EnumValue:
    key: str
    names: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class SeedAttribute:
    key: str
    names: Mapping[str, str]
    data_type: AttributeType
    enum_values: tuple[EnumValue, ...] | None  # in display order
    unit: str | None
    constraints: Mapping[str, int | float]


@dataclass(frozen=True, slots=True)
class CategoryAttribute:
    key: str
    is_required: bool
    is_filterable: bool


@dataclass(frozen=True, slots=True)
class SeedCategory:
    key: str
    parent_key: str | None
    path: str
    names: Mapping[str, str]
    icon: str | None
    position: int
    is_active: bool
    is_leaf: bool
    is_restricted: bool
    vertical: Vertical
    transaction_model: TransactionModel
    shipping_allowed: bool
    max_photos: int
    brand_policy: BrandPolicy
    allowed_conditions: tuple[str, ...] | None
    attributes: tuple[CategoryAttribute, ...]


@dataclass(frozen=True, slots=True)
class CatalogSeed:
    attributes: tuple[SeedAttribute, ...]
    categories: tuple[SeedCategory, ...]  # parents before their children

    def category(self, key: str) -> SeedCategory:
        return next(c for c in self.categories if c.key == key)

    def attribute(self, key: str) -> SeedAttribute:
        return next(a for a in self.attributes if a.key == key)


class _StrictLoader(yaml.SafeLoader):
    """Refuses a key written twice in one mapping (PyYAML keeps the last one silently)."""


def _mapping_without_duplicates(loader: _StrictLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    keys: list[object] = [
        loader.construct_object(key)  # pyright: ignore[reportUnknownMemberType]
        for key, _ in node.value
    ]
    if duplicates := sorted({str(k) for k in keys if keys.count(k) > 1}):
        raise SeedError(f"clé écrite deux fois {duplicates} ({node.start_mark})")
    return loader.construct_mapping(node)  # pyright: ignore[reportUnknownMemberType]


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_without_duplicates
)


def parse_yaml(source: str) -> Any:
    return yaml.load(source, Loader=_StrictLoader)  # noqa: S506 — a SafeLoader subclass


def read_seed_file(name: str) -> Any:
    """A YAML file of `catalog/seed`, shipped inside the package."""
    source = resources.files("trovelya.modules.catalog").joinpath("seed", name)
    return parse_yaml(source.read_text(encoding="utf-8"))


def load_seed() -> CatalogSeed:
    return parse_seed(read_seed_file("categories.yaml"))


def _labels(value: object, where: str) -> dict[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise SeedError(f"{where} : libellé `fr` manquant ou vide")
    return {"fr": value}


def _parse_attribute(key: object, spec: object) -> SeedAttribute:
    if not isinstance(key, str) or not _ATTRIBUTE_KEY.fullmatch(key):
        raise SeedError(f"attribut {key!r} : clé invalide")
    if not isinstance(spec, dict):
        raise SeedError(f"attribut {key} : définition invalide")
    spec = cast(dict[str, Any], spec)
    if unknown := set(spec) - _ATTRIBUTE_FIELDS:
        raise SeedError(f"attribut {key} : champ inconnu {sorted(unknown)}")
    data_type = spec.get("type")
    if data_type not in get_args(AttributeType):
        raise SeedError(f"attribut {key} : type {data_type!r} invalide")
    values = spec.get("values")
    enum_values: tuple[EnumValue, ...] | None = None
    if data_type == "enum":
        if not isinstance(values, dict) or not values:
            raise SeedError(f"attribut {key} : un attribut enum exige des values")
        parsed: list[EnumValue] = []
        for value_key, label in cast(dict[object, object], values).items():
            if not isinstance(value_key, str) or not _VALUE_KEY.fullmatch(value_key):
                raise SeedError(f"attribut {key} : clé de values {value_key!r} invalide")
            if not isinstance(label, str) or not label:
                raise SeedError(f"attribut {key} : libellé de values {value_key} invalide")
            parsed.append(EnumValue(value_key, {"fr": label}))
        enum_values = tuple(parsed)
    elif values is not None:
        raise SeedError(f"attribut {key} : values réservées au type enum")
    constraints = _parse_constraints(key, str(data_type), spec)
    unit = spec.get("unit")
    if unit is not None and not isinstance(unit, str):
        raise SeedError(f"attribut {key} : unit doit être un texte")
    return SeedAttribute(
        key=key,
        names=_labels(spec.get("fr"), f"attribut {key}"),
        data_type=cast(AttributeType, data_type),
        enum_values=enum_values,
        unit=unit,
        constraints=constraints,
    )


def _is_conditions(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    conditions = cast(list[object], value)
    return len(set(map(str, conditions))) == len(conditions) and all(
        c in ItemCondition.__members__.values() for c in conditions
    )


_SETTING_CHECKS: dict[str, Callable[[object], bool]] = {
    "vertical": lambda v: v in get_args(Vertical),
    "model": lambda v: v in get_args(TransactionModel),
    "brand": lambda v: v in get_args(BrandPolicy),
    "shipping": lambda v: isinstance(v, bool),
    "restricted": lambda v: isinstance(v, bool),
    "max_photos": lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 50,
    "conditions": _is_conditions,
}


_ALLOWED_CONSTRAINTS: dict[str, frozenset[str]] = {
    "text": frozenset({"max_length"}),
    "int": frozenset({"min", "max", "step"}),
    "decimal": frozenset({"min", "max", "step"}),
    "year": frozenset({"min", "max"}),
    "enum": frozenset(),
    "bool": frozenset(),
}


def _parse_constraints(key: str, data_type: str, spec: Mapping[str, Any]) -> dict[str, int | float]:
    """Bounds that fit the type: whole numbers for int, year and max_length, finite numbers,
    min ≤ max, a positive step."""
    constraints: dict[str, int | float] = {}
    for name in _CONSTRAINTS:
        if name not in spec:
            continue
        if name not in _ALLOWED_CONSTRAINTS[data_type]:
            raise SeedError(f"attribut {key} : {name} ne convient pas au type {data_type}")
        bound = spec[name]
        whole = data_type in {"int", "year"} or name == "max_length"
        if (
            isinstance(bound, bool)
            or not isinstance(bound, int | float)
            or not math.isfinite(bound)
            or (whole and not isinstance(bound, int))
        ):
            raise SeedError(f"attribut {key} : {name} invalide ({bound!r})")
        constraints[name] = bound
    if "min" in constraints and "max" in constraints and constraints["min"] > constraints["max"]:
        raise SeedError(f"attribut {key} : min supérieur à max")
    if constraints.get("step", 1) <= 0 or constraints.get("max_length", 1) <= 0:
        raise SeedError(f"attribut {key} : step et max_length doivent être positifs")
    return constraints


def _check_setting(key: str, field: str, value: object) -> None:
    if not _SETTING_CHECKS[field](value):
        raise SeedError(f"{key} : valeur de {field} invalide ({value!r})")


def _parse_attribute_refs(
    key: str, refs: object, known: Mapping[str, SeedAttribute]
) -> list[CategoryAttribute]:
    if not isinstance(refs, list):
        raise SeedError(f"{key} : attributes doit être une liste")
    parsed: list[CategoryAttribute] = []
    for ref in cast(list[object], refs):
        if not isinstance(ref, str):
            raise SeedError(f"{key} : attribut {ref!r} invalide")
        name = ref.rstrip("!~")
        if name not in known or len(ref) - len(name) > 1:
            raise SeedError(f"{key} : attribut inconnu {ref!r}")
        parsed.append(CategoryAttribute(name, ref.endswith("!"), not ref.endswith("~")))
    return parsed


def _merge(
    inherited: Sequence[CategoryAttribute], own: Sequence[CategoryAttribute]
) -> tuple[CategoryAttribute, ...]:
    """Own attributes are added after the inherited ones; one named again overrides its flags
    in place."""
    merged = {a.key: a for a in inherited}
    for attribute in own:
        merged[attribute.key] = attribute
    return tuple(merged.values())


def parse_seed(document: object) -> CatalogSeed:
    """Validate a seed document entirely and resolve inheritance; raise `SeedError`."""
    if not isinstance(document, dict):
        raise SeedError("document invalide")
    document = cast(dict[str, Any], document)
    if document.get("version") != SEED_VERSION:
        raise SeedError(f"version {document.get('version')!r} non prise en charge")
    raw_attributes = document.get("attributes")
    if not isinstance(raw_attributes, dict):
        raise SeedError("attributes manquants")
    attributes = {
        a.key: a
        for a in (
            _parse_attribute(k, v) for k, v in cast(dict[object, object], raw_attributes).items()
        )
    }
    roots = document.get("categories")
    if not isinstance(roots, list):
        raise SeedError("categories manquantes")
    root_keys = [
        cast(dict[str, object], r).get("key") if isinstance(r, dict) else None
        for r in cast(list[object], roots)
    ]
    if tuple(root_keys) != UNIVERSE_KEYS:
        raise SeedError(f"les racines doivent être les 16 univers, dans l'ordre : {root_keys}")

    categories: list[SeedCategory] = []
    seen_keys: set[str] = set()
    seen_paths: set[str] = set()

    def visit(
        node: object, parent: SeedCategory | None, settings: dict[str, Any], position: int
    ) -> None:
        if not isinstance(node, dict):
            raise SeedError(f"catégorie invalide sous {parent.key if parent else 'la racine'}")
        node = cast(dict[str, Any], node)
        key = node.get("key")
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise SeedError(f"clé de catégorie invalide : {key!r}")
        if unknown := set(node) - _NODE_FIELDS:
            raise SeedError(f"{key} : champ inconnu {sorted(unknown)}")
        if key in seen_keys:
            raise SeedError(f"{key} : clé en doublon")
        seen_keys.add(key)
        label = key.rsplit(".", 1)[-1]
        if parent is None:
            path = key
            if missing := [f for f in _ROOT_REQUIRED if f not in node]:
                raise SeedError(f"{key} : réglage obligatoire manquant {missing}")
        else:
            path = f"{parent.path}.{label}"
            expected_prefix = key.rsplit(".", 1)[0] if "." in key else None
            if expected_prefix != parent.key and node.get("moved") is not True:
                raise SeedError(
                    f"{key} : la clé ne commence pas par celle du parent {parent.key}"
                    " (ajouter `moved: true` pour une catégorie déplacée)"
                )
        if path in seen_paths:
            raise SeedError(f"{key} : clé en doublon dans le même parent ({path})")
        seen_paths.add(path)
        own = dict(settings)
        for field in _INHERITED:
            if field in node:
                _check_setting(key, field, node[field])
                own[field] = node[field]
        inherited_attributes = () if node.get("attributes_replace") is True else settings["attrs"]
        own["attrs"] = _merge(
            inherited_attributes, _parse_attribute_refs(key, node.get("attributes", []), attributes)
        )
        children = node.get("children", [])
        if not isinstance(children, list):
            raise SeedError(f"{key} : children doit être une liste")
        children = cast(list[object], children)
        if parent is None and not children:
            raise SeedError(f"l'univers {key} doit contenir au moins une feuille")
        active = node.get("active", True)
        if not isinstance(active, bool):
            raise SeedError(f"{key} : active doit être vrai ou faux")
        # Retiring a category retires its subtree; an active category keeps an active child or
        # becomes a leaf, so the tree served never changes shape by accident.
        if parent is not None and not parent.is_active:
            active = False
        if (
            active
            and children
            and all(
                isinstance(c, dict) and cast(dict[str, object], c).get("active") is False
                for c in children
            )
        ):
            raise SeedError(
                f"{key} : tous ses enfants sont retirés ; retirer aussi {key} ou garder un enfant"
            )
        icon = node.get("icon")
        if icon is not None and not isinstance(icon, str):
            raise SeedError(f"{key} : icon doit être un texte")
        conditions = own.get("conditions")
        category = SeedCategory(
            key=key,
            parent_key=parent.key if parent else None,
            path=path,
            names=_labels(node.get("fr"), key),
            icon=icon,
            position=position,
            is_active=active,
            is_leaf=not children,
            is_restricted=bool(own.get("restricted", False)),
            vertical=own["vertical"],
            transaction_model=own["model"],
            shipping_allowed=own["shipping"],
            max_photos=own["max_photos"],
            brand_policy=own["brand"],
            allowed_conditions=tuple(conditions) if conditions else None,
            attributes=own["attrs"],
        )
        categories.append(category)
        for index, child in enumerate(children):
            visit(child, category, own, index)

    for index, root in enumerate(cast(list[object], roots)):
        visit(root, None, {"attrs": ()}, index)
    return CatalogSeed(attributes=tuple(attributes.values()), categories=tuple(categories))
