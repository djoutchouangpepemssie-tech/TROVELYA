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


def test_valid_values_kept_in_the_category_order() -> None:
    values, errors = validate_attributes(
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
    values, errors = validate_attributes({"color": "blanc", "isbn": None}, RULES)
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
    ],
)
def test_attribute_validation(given: dict[str, Any], error: tuple[str, str]) -> None:
    _, errors = validate_attributes({"color": "noir"} | given, RULES)
    assert error in errors


def test_every_error_is_reported_at_once() -> None:
    _, errors = validate_attributes({"shoe_eu": 99, "brand_new": 1}, RULES)
    assert sorted(errors) == [
        ("brand_new", "unknown"),
        ("color", "required"),
        ("shoe_eu", "too_large"),
    ]
