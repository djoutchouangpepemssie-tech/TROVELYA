"""The quality of a listing (P2-T07, plan Q42): 0 to 100 from its photos, description, optional
attributes and brand, with the tips that would raise it, the most rewarding first."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trovelya.modules.catalog.service.quality import DEFAULT_FORMULA, Facts, Formula, quality

FULL = "x" * 300


def _facts(**changes: object) -> Facts:
    base: dict[str, object] = {
        "photos": 1,
        "description_length": 20,
        "missing_attributes": (("material", "Matière"), ("color", "Couleur")),
        "optional_attributes": 2,
        "brand_expected": True,
        "has_brand": False,
    }
    return Facts(**(base | changes))  # type: ignore[arg-type]


def test_quality_examples() -> None:
    """A minimal listing: one photo (15), a short description (0), no optional attribute (0),
    no brand where one is expected (0); a complete one scores 100."""
    assert quality(_facts(), DEFAULT_FORMULA).score == 15
    assert quality(_facts(brand_expected=False), DEFAULT_FORMULA).score == 25
    complete = _facts(photos=6, description_length=300, missing_attributes=(), has_brand=True)
    assert quality(complete, DEFAULT_FORMULA).score == 100
    assert quality(complete, DEFAULT_FORMULA).tips == ()


def test_points_of_each_criterion() -> None:
    assert quality(_facts(photos=3, brand_expected=False), DEFAULT_FORMULA).score == 35
    assert quality(_facts(photos=9, brand_expected=False), DEFAULT_FORMULA).score == 50  # 6 max
    half = _facts(description_length=160, brand_expected=False)
    assert quality(half, DEFAULT_FORMULA).score == 25 + 15
    one = _facts(missing_attributes=(("color", "Couleur"),), brand_expected=False)
    assert quality(one, DEFAULT_FORMULA).score == 25 + 10
    none_to_fill = _facts(missing_attributes=(), optional_attributes=0, brand_expected=False)
    assert quality(none_to_fill, DEFAULT_FORMULA).score == 15 + 20 + 10  # nothing to fill: acquired


def test_quality_tips_ordered_by_gain() -> None:
    tips = quality(_facts(description_length=160), DEFAULT_FORMULA).tips
    assert [(t.code, t.gain) for t in tips] == [
        ("photos", 25),
        ("description", 15),
        ("brand", 10),
        ("attribute", 10),
        ("attribute", 10),
    ]
    assert (tips[0].count, tips[3].attribute, tips[3].label) == (5, "material", "Matière")


@given(
    photos=st.integers(0, 50),
    length=st.integers(0, 5000),
    missing=st.integers(0, 30),
    extra=st.integers(0, 30),
    brand_expected=st.booleans(),
    has_brand=st.booleans(),
)
def test_quality_bounds(
    photos: int, length: int, missing: int, extra: int, brand_expected: bool, has_brand: bool
) -> None:
    facts = Facts(
        photos=photos,
        description_length=length,
        missing_attributes=tuple((f"a{i}", f"A{i}") for i in range(missing)),
        optional_attributes=missing + extra,
        brand_expected=brand_expected,
        has_brand=has_brand,
    )
    found = quality(facts, DEFAULT_FORMULA)
    assert 0 <= found.score <= 100
    assert found.score + sum(t.gain for t in found.tips) == pytest.approx(100, abs=len(found.tips))


def test_formula_must_total_100() -> None:
    with pytest.raises(ValueError, match="100"):
        Formula.parse(DEFAULT_FORMULA.raw | {"brand": 20})
    assert Formula.parse(DEFAULT_FORMULA.raw) == DEFAULT_FORMULA
