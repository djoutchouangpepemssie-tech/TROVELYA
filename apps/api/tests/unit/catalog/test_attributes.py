"""Attribute values checked against the category's attributes (P2-T03b1, section 7.5):
types, lists, bounds, steps, lengths, required ones; anything else is refused."""

from typing import Any

import pytest

from trovelya.modules.catalog.service.attributes import AttributeRule, validate_attributes

RULES = (
    AttributeRule("color", "enum", is_required=True, enum_keys=frozenset({"noir", "blanc"})),
    AttributeRule("shoe_eu", "decimal", constraints={"min": 15, "max": 52, "step": 0.5}),
    AttributeRule("width_cm", "int", constraints={"min": 1, "max": 2000}),
    AttributeRule("isbn", "text", constraints={"max_length": 17}),
    AttributeRule("edition_year", "year", constraints={"min": 1450}),
    AttributeRule("first_edition", "bool"),
)


YEAR = 2026  # the clock's year: `year` attributes go up to the next one (plan P2, Q21)
INT32_MAX = 2**31 - 1


def check(
    values: dict[str, Any], rules: tuple[AttributeRule, ...] = RULES
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    return validate_attributes(values, rules, current_year=YEAR)


def test_valid_values_kept_in_the_category_order() -> None:
    values, errors = check(
        {
            "first_edition": True,
            "isbn": "  978-2-07-036024-5 ",
            "color": "noir",
            "shoe_eu": 42.5,
            "width_cm": 30,
            "edition_year": 1957,
        },
        RULES,
    )
    assert errors == []
    assert list(values.items()) == [
        ("color", "noir"),
        ("shoe_eu", 42.5),
        ("width_cm", 30),
        ("isbn", "978-2-07-036024-5"),
        ("edition_year", 1957),
        ("first_edition", True),
    ]


def test_optional_attributes_may_be_absent_or_null() -> None:
    values, errors = check({"color": "blanc", "isbn": None}, RULES)
    assert (values, errors) == ({"color": "blanc"}, [])


@pytest.mark.parametrize(
    ("given", "error"),
    [
        ({"color": None}, ("color", "required")),
        ({"color": "violet"}, ("color", "not_in_list")),
        ({"color": 3}, ("color", "type")),
        ({"shoe_eu": 14.5}, ("shoe_eu", "too_small")),
        ({"shoe_eu": 52.5}, ("shoe_eu", "too_large")),
        ({"shoe_eu": 42.3}, ("shoe_eu", "step")),
        ({"shoe_eu": "42"}, ("shoe_eu", "type")),
        ({"shoe_eu": float("nan")}, ("shoe_eu", "type")),
        ({"width_cm": 0}, ("width_cm", "too_small")),
        ({"width_cm": 2001}, ("width_cm", "too_large")),
        ({"width_cm": 12.5}, ("width_cm", "type")),
        ({"width_cm": True}, ("width_cm", "type")),
        ({"isbn": "9" * 18}, ("isbn", "too_long")),
        ({"isbn": "   "}, ("isbn", "empty")),
        ({"isbn": 978}, ("isbn", "type")),
        ({"edition_year": 1449}, ("edition_year", "too_small")),
        ({"edition_year": "1957"}, ("edition_year", "type")),
        ({"first_edition": "oui"}, ("first_edition", "type")),
        ({"first_edition": 1}, ("first_edition", "type")),
        ({"size_eu": 42}, ("size_eu", "unknown")),
        ({"width_cm": 10**400}, ("width_cm", "too_large")),
        ({"shoe_eu": 10**400}, ("shoe_eu", "too_large")),
        ({"isbn": "978\x00"}, ("isbn", "invalid_characters")),
        ({"isbn": "978\n2"}, ("isbn", "invalid_characters")),
        ({"isbn": " \u200b "}, ("isbn", "empty")),
    ],
)
def test_attribute_validation(given: dict[str, Any], error: tuple[str, str]) -> None:
    _, errors = check({"color": "noir"} | given, RULES)
    assert error in errors


def test_every_error_is_reported_at_once() -> None:
    _, errors = check({"shoe_eu": 99, "brand_new": 1}, RULES)
    assert sorted(errors) == [
        ("brand_new", "unknown"),
        ("color", "required"),
        ("shoe_eu", "too_large"),
    ]


@pytest.mark.parametrize(
    "given", [{"shoe_eu": 15}, {"shoe_eu": 52}, {"width_cm": 1}, {"width_cm": 2000}]
)
def test_bounds_are_inclusive(given: dict[str, Any]) -> None:
    assert check({"color": "noir"} | given, RULES)[1] == []


def test_step_counted_from_the_minimum() -> None:
    rules = (AttributeRule("odd", "int", constraints={"min": 1, "step": 2}),)
    assert check({"odd": 3}, rules)[1] == []
    assert check({"odd": 4}, rules)[1] == [("odd", "step")]


def test_step_counted_from_zero_without_a_minimum() -> None:
    rules = (AttributeRule("dozens", "int", constraints={"step": 12}),)
    assert check({"dozens": 24}, rules)[1] == []
    assert check({"dozens": 25}, rules)[1] == [("dozens", "step")]


def test_invisible_characters_dropped_from_text() -> None:
    values, _ = check({"color": "noir", "isbn": "978\u200b-2"}, RULES)
    assert values["isbn"] == "978-2"


@pytest.mark.parametrize(
    ("given", "error"),
    [
        ({"edition_year": YEAR + 1}, None),  # next year's models are sold in advance
        ({"edition_year": YEAR + 2}, ("edition_year", "too_large")),
        ({"edition_year": 10**30}, ("edition_year", "too_large")),
    ],
)
def test_years_end_next_year(given: dict[str, Any], error: tuple[str, str] | None) -> None:
    assert check({"color": "noir"} | given)[1] == ([error] if error else [])


def test_year_bound_follows_the_clock() -> None:
    values = {"color": "noir", "edition_year": 2028}
    assert validate_attributes(values, RULES, current_year=2027)[1] == []


def test_seed_maximum_kept_when_lower_than_next_year() -> None:
    rules = (AttributeRule("vintage", "year", constraints={"min": 1900, "max": 2000}),)
    assert check({"vintage": 2001}, rules)[1] == [("vintage", "too_large")]


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (INT32_MAX, None),
        (INT32_MAX + 1, "too_large"),
        (-(2**31), None),
        (-(2**31) - 1, "too_small"),
    ],
)
def test_integers_fit_in_32_bits(value: int, error: str | None) -> None:
    rules = (AttributeRule("count", "int"),)  # no bound in the seed
    assert check({"count": value}, rules)[1] == ([("count", error)] if error else [])


def test_unknown_type_is_a_bug() -> None:
    rules = (AttributeRule("odd", "colour", constraints={}),)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown type"):
        check({"odd": 1}, rules)
