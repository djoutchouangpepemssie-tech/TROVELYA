"""Common brands offered by autocompletion: `seed/brands.yaml` (P2-T01b, decision Q3)."""

import re
import unicodedata
from typing import Any, cast

from trovelya.modules.catalog.service.seed import SeedError


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def parse_brands(document: object) -> tuple[tuple[str, str], ...]:
    """(name, slug) pairs of `seed/brands.yaml`; raise `SeedError`."""
    if not isinstance(document, dict) or cast(dict[str, Any], document).get("version") != 1:
        raise SeedError("brands.yaml : version 1 attendue")
    names = cast(dict[str, Any], document).get("brands")
    if not isinstance(names, list):
        raise SeedError("brands.yaml : liste brands manquante")
    pairs: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    seen_slugs: set[str] = set()
    for name in cast(list[object], names):
        if not isinstance(name, str) or not 1 <= len(name) <= 80:
            raise SeedError(f"brands.yaml : nom invalide {name!r}")
        slug = slugify(name)
        if not slug or name.casefold() in seen_names or slug in seen_slugs:
            raise SeedError(f"brands.yaml : {name!r} en doublon ou sans slug")
        seen_names.add(name.casefold())
        seen_slugs.add(slug)
        pairs.append((name, slug))
    return tuple(pairs)
