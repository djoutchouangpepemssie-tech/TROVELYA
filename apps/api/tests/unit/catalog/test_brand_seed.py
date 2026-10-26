"""The common brands file (P2-T01b, decision Q3)."""

import pytest

from trovelya.modules.catalog.service.brand_seed import parse_brands, slugify
from trovelya.modules.catalog.service.seed import SeedError, read_seed_file


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Hermès", "hermes"),
        ("Saint Laurent", "saint-laurent"),
        ("A.P.C.", "a-p-c"),
        ("Dr. Martens", "dr-martens"),
        ("H&M", "h-m"),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_brands_file_valid() -> None:
    brands = parse_brands(read_seed_file("brands.yaml"))
    assert len(brands) == 372
    assert ("Hermès", "hermes") in brands and ("& Other Stories", "other-stories") in brands


@pytest.mark.parametrize(
    "names",
    [["Apple", "apple"], ["H&M", "H-M"], ["", "Zara"], ["x" * 81], [3]],
)
def test_brands_duplicates_and_invalid_names_refused(names: list[object]) -> None:
    with pytest.raises(SeedError):
        parse_brands({"version": 1, "brands": names})
