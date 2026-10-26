"""Attribute values of a listing, checked against its category's attributes (section 7.5,
`category_attributes`, the seed's types and bounds).

Every error is reported at once, as `(attribute key, code)`; the accepted values are returned in
the category's order, text trimmed. Codes: `required`, `unknown` (not an attribute of the
category), `type`, `not_in_list`, `too_small`, `too_large`, `step` (exact decimal arithmetic:
0.1 + 0.2 is not a multiple of 0.1), `too_long`, `empty`, `invalid_characters`.

Bounds beyond the seed's (plan P2, Q21): `int` and `year` fit in a signed 32-bit integer, and a
`year` is at most the clock's year + 1 (next year's models are sold in advance).
"""

import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from trovelya.modules.catalog.models import AttributeType

AttributeIssue = tuple[str, str]

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


@dataclass(frozen=True)
class AttributeRule:
    key: str
    data_type: AttributeType
    is_required: bool = False
    enum_keys: frozenset[str] | None = None
    constraints: Mapping[str, int | float] = field(default_factory=dict[str, int | float])


def _is_number(value: Any) -> bool:
    """A JSON number: never a boolean, never NaN or an infinity (a huge integer is a number)."""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, float) and math.isfinite(value))


def _clean_text(value: str) -> str | None:
    """Trimmed text without its invisible format characters; None when it holds a control
    character (PostgreSQL refuses NUL in JSONB, the brand search refuses the same)."""
    if any(unicodedata.category(c) == "Cc" for c in value):
        return None
    return "".join(c for c in value if unicodedata.category(c) != "Cf").strip()


def _check_bounds(value: int | float, constraints: Mapping[str, int | float]) -> str | None:
    if "min" in constraints and value < constraints["min"]:
        return "too_small"
    if "max" in constraints and value > constraints["max"]:
        return "too_large"
    step = constraints.get("step")
    if step is not None:
        # Exact decimal arithmetic: 42.3 is not a multiple of 0.5, 42.5 is.
        start = Decimal(str(constraints.get("min", 0)))
        if (Decimal(str(value)) - start) % Decimal(str(step)) != 0:
            return "step"
    return None


def _check_integer(rule: AttributeRule, value: int, current_year: int) -> str | None:
    """32 bits first, then the seed's bounds, a year's maximum lowered to next year."""
    if value < INT32_MIN:
        return "too_small"
    if value > INT32_MAX:
        return "too_large"
    constraints = rule.constraints
    if rule.data_type == "year":
        constraints = {
            **constraints,
            "max": min(constraints.get("max", math.inf), current_year + 1),
        }
    return _check_bounds(value, constraints)


def _check(rule: AttributeRule, value: Any, current_year: int) -> tuple[Any, str | None]:
    """The value to store, or the error code."""
    match rule.data_type:
        case "enum":
            if not isinstance(value, str):
                return None, "type"
            return value, None if value in (rule.enum_keys or frozenset()) else "not_in_list"
        case "bool":
            return value, None if isinstance(value, bool) else "type"
        case "text":
            if not isinstance(value, str):
                return None, "type"
            text = _clean_text(value)
            if text is None:
                return None, "invalid_characters"
            if not text:
                return None, "empty"
            if len(text) > rule.constraints.get("max_length", math.inf):
                return None, "too_long"
            return text, None
        case "int" | "year":
            if not _is_number(value) or not isinstance(value, int):
                return None, "type"
            return value, _check_integer(rule, value, current_year)
        case "decimal":
            if not _is_number(value):
                return None, "type"
            return value, _check_bounds(value, rule.constraints)
        case _:  # a type the seed does not know: a bug, not the member's mistake
            raise ValueError(f"attribute {rule.key}: unknown type {rule.data_type!r}")


def validate_attributes(
    values: Mapping[str, Any], rules: Sequence[AttributeRule], *, current_year: int
) -> tuple[dict[str, Any], list[AttributeIssue]]:
    """Accepted values (category order) and every error found; `current_year` comes from the
    clock."""
    accepted: dict[str, Any] = {}
    errors: list[AttributeIssue] = []
    known = {rule.key for rule in rules}
    errors.extend((key, "unknown") for key in values if key not in known)
    for rule in rules:
        value = values.get(rule.key)
        if value is None:
            if rule.is_required:
                errors.append((rule.key, "required"))
            continue
        stored, error = _check(rule, value, current_year)
        if error:
            errors.append((rule.key, error))
        else:
            accepted[rule.key] = stored
    return accepted, errors
