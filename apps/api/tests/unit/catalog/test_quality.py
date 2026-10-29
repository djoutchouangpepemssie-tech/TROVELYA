"""The quality of a listing (P2-T07, plan Q42): 0 to 100 from its photos, description, optional
attributes and brand, with the tips that would raise it, each worth exactly what it adds."""

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trovelya.modules.catalog.service.quality import DEFAULT_FORMULA, Facts, Formula, quality

OPTIONAL = (("material", "Matière"), ("color", "Couleur"))


def _facts(**changes: Any) -> Facts:
    base: dict[str, Any] = {
        "photos": 1,
        "max_photos": 12,
        "description": "x" * 20,
        "attributes": {},
        "optional_attributes": OPTIONAL,
        "brand_expected": True,
        "has_brand": False,
    }
    return Facts(**(base | changes))


def _score(**changes: Any) -> int:
    return quality(_facts(**changes), DEFAULT_FORMULA).score


def _raw(**change: Any) -> dict[str, Any]:
    return DEFAULT_FORMULA.model_dump(by_alias=True) | change


def test_quality_examples() -> None:
    """A minimal listing: one photo (15), a short description, no optional attribute, no brand
    where one is expected; 25 where none is; a complete one scores 100, with no tip."""
    assert _score() == 15
    assert _score(brand_expected=False) == 25
    complete = _facts(
        photos=6,
        description="x" * 300,
        attributes={"material": "lin", "color": "bleu"},
        has_brand=True,
    )
    assert quality(complete, DEFAULT_FORMULA).score == 100
    assert quality(complete, DEFAULT_FORMULA).tips == ()


def test_points_of_each_criterion() -> None:
    assert _score(photos=3, brand_expected=False) == 35
    assert _score(photos=9, brand_expected=False) == 50  # six at most
    assert _score(photos=0, brand_expected=False) == 10
    assert _score(description="x" * 160, brand_expected=False) == 25 + 15
    assert _score(attributes={"color": "bleu"}, brand_expected=False) == 25 + 10
    assert _score(optional_attributes=(), brand_expected=False) == 15 + 20 + 10  # acquired


def test_photos_reached_at_the_category_maximum() -> None:
    """Q42: a category allowing three photos gives the 40 points at three."""
    assert _score(photos=3, max_photos=3, brand_expected=False) == 50
    assert _score(photos=1, max_photos=3, brand_expected=False) == 10 + 24
    tips = quality(_facts(photos=1, max_photos=3), DEFAULT_FORMULA).tips
    assert next(t for t in tips if t.code == "photos").count == 2


def test_false_and_zero_are_answers() -> None:
    assert _score(attributes={"material": False, "color": 0}, brand_expected=False) == 45
    assert _score(attributes={"material": None}, brand_expected=False) == 25


def test_blanks_count_once() -> None:
    assert _score(description="a" + " " * 298 + "b", brand_expected=False) == 25
    assert _score(description="  " + "x" * 160 + "\n\n", brand_expected=False) == 40


def test_half_points_rounded_up() -> None:
    eight = tuple((f"a{i}", f"A{i}") for i in range(8))
    base: dict[str, Any] = {"optional_attributes": eight, "brand_expected": False}
    assert _score(attributes={f"a{i}": 1 for i in range(7)}, **base) == 43  # 42.5
    assert _score(attributes={f"a{i}": 1 for i in range(5)}, **base) == 38  # 37.5


def test_quality_tips_ordered_by_gain() -> None:
    tips = quality(_facts(description="x" * 160), DEFAULT_FORMULA).tips
    assert [(t.code, t.gain) for t in tips] == [
        ("photos", 25),
        ("description", 15),
        ("brand", 10),
        ("attribute", 10),
        ("attribute", 10),
    ]
    assert (tips[0].count, tips[3].attribute, tips[3].label) == (5, "material", "Matière")


def test_no_tip_worth_nothing() -> None:
    no_brand = Formula.parse(_raw(brand=0, attributes=30))
    assert "brand" not in [t.code for t in quality(_facts(), no_brand).tips]
    many = tuple((f"a{i}", f"A{i}") for i in range(60))
    assert all(t.gain > 0 for t in quality(_facts(optional_attributes=many), DEFAULT_FORMULA).tips)


@given(
    photos=st.integers(0, 50),
    max_photos=st.integers(1, 50),
    length=st.integers(0, 600),
    optional=st.integers(0, 30),
    filled=st.integers(0, 30),
    brand_expected=st.booleans(),
    has_brand=st.booleans(),
)
def test_quality_bounds_and_exact_gains(
    photos: int,
    max_photos: int,
    length: int,
    optional: int,
    filled: int,
    brand_expected: bool,
    has_brand: bool,
) -> None:
    """Each tip is worth exactly what following it adds, never more than is left."""
    facts = _facts(
        photos=photos,
        max_photos=max_photos,
        description="x" * length,
        attributes={f"a{i}": 1 for i in range(min(filled, optional))},
        optional_attributes=tuple((f"a{i}", f"A{i}") for i in range(optional)),
        brand_expected=brand_expected,
        has_brand=has_brand,
    )
    found = quality(facts, DEFAULT_FORMULA)
    assert 0 <= found.score <= 100
    assert all(0 < tip.gain <= 100 - found.score for tip in found.tips)


@pytest.mark.parametrize(
    "change",
    [
        {"brand": 20},  # 110 in all
        {"brand": 10.9},  # a float
        {"brand": True},  # a boolean
        {"brand": -10, "attributes": 40},  # negative
        {"photos": {"first": 50, "each": -2, "up_to": 6}},
        {"photos": {"first": 40, "each": 0, "up_to": 0}},
        {"extra": 1},
    ],
)
def test_formula_strictly_checked(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="quality_formula"):
        Formula.parse(_raw(**change))


def test_formula_with_a_missing_key_refused() -> None:
    raw = _raw()
    del raw["brand"]
    with pytest.raises(ValueError, match="quality_formula"):
        Formula.parse(raw)
