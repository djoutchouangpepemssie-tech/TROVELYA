"""Attribute values of a listing, checked against its category's attributes (section 7.5,
`category_attributes`, the seed's types and bounds).

Every error is reported at once, as `(attribute key, code)`; the accepted values are returned in
the category's order, text trimmed. Codes: `required`, `unknown` (not an attribute of the
category), `type`, `not_in_list`, `too_small`, `too_large`, `step`, `too_long`, `empty`.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from trovelya.modules.catalog.models import AttributeType

AttributeError_ = tuple[str, str]


@dataclass(frozen=True)
class AttributeRule:
    key: str
    data_type: AttributeType
    is_required: bool = False
    enum_keys: frozenset[str] | None = None
    constraints: Mapping[str, int | float] = field(default_factory=dict[str, int | float])


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


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


def _check(rule: AttributeRule, value: Any) -> tuple[Any, str | None]:
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
            text = value.strip()
            if not text:
                return None, "empty"
            if len(text) > rule.constraints.get("max_length", math.inf):
                return None, "too_long"
            return text, None
        case "int" | "year":
            if not _is_number(value) or not isinstance(value, int):
                return None, "type"
            return value, _check_bounds(value, rule.constraints)
        case "decimal":
            if not _is_number(value):
                return None, "type"
            return value, _check_bounds(value, rule.constraints)


def validate_attributes(
    values: Mapping[str, Any], rules: Sequence[AttributeRule]
) -> tuple[dict[str, Any], list[AttributeError_]]:
    """Accepted values (category order) and every error found."""
    accepted: dict[str, Any] = {}
    errors: list[AttributeError_] = []
    known = {rule.key for rule in rules}
    errors.extend((key, "unknown") for key in values if key not in known)
    for rule in rules:
        value = values.get(rule.key)
        if value is None:
            if rule.is_required:
                errors.append((rule.key, "required"))
            continue
        stored, error = _check(rule, value)
        if error:
            errors.append((rule.key, error))
        else:
            accepted[rule.key] = stored
    return accepted, errors
