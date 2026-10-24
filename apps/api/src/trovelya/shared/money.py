"""Money as integer minor units plus an ISO 4217 currency (sections 5.9 and ADR-0005).

Never a float. Rounding is always explicit:
- `percent_bp_ceil` rounds up: fees charged to the buyer;
- `percent_bp_floor` rounds down: amounts paid out (in favour of the payee).
"""

import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Self

_CURRENCY = re.compile(r"^[A-Z]{3}$")
BASIS_POINTS_PER_UNIT = 10_000


class CurrencyMismatchError(ValueError):
    """Raised when two amounts in different currencies are combined or compared."""


def _require_int(value: object, name: str) -> int:
    # `type(...) is int` also rejects bool, a subclass of int.
    if type(value) is not int:
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    return value


def ceil_div(numerator: int, denominator: int) -> int:
    """Integer division rounded towards +infinity."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return -(-numerator // denominator)


def floor_div(numerator: int, denominator: int) -> int:
    """Integer division rounded towards -infinity."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return numerator // denominator


@total_ordering
@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        _require_int(self.amount_minor, "amount_minor")
        # Runtime guard: callers may pass anything despite the annotation.
        is_str = isinstance(self.currency, str)  # pyright: ignore[reportUnnecessaryIsInstance]
        if not is_str or not _CURRENCY.match(self.currency):
            raise ValueError(f"currency must be an ISO 4217 code, got {self.currency!r}")

    @classmethod
    def zero(cls, currency: str) -> Self:
        return cls(0, currency)

    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"{self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount_minor < other.amount_minor


def _percent_inputs(amount: Money, bp: int) -> None:
    _require_int(bp, "bp")
    if not 0 <= bp <= BASIS_POINTS_PER_UNIT:
        raise ValueError("basis points must be between 0 and 10000")
    if amount.amount_minor < 0:
        raise ValueError("percentage of a negative amount is not defined")


def percent_bp_ceil(amount: Money, bp: int) -> Money:
    """`amount * bp / 10000`, rounded UP to the minor unit. Use for fees charged to the buyer."""
    _percent_inputs(amount, bp)
    return Money(ceil_div(amount.amount_minor * bp, BASIS_POINTS_PER_UNIT), amount.currency)


def percent_bp_floor(amount: Money, bp: int) -> Money:
    """`amount * bp / 10000`, rounded DOWN to the minor unit. Use for amounts paid out."""
    _percent_inputs(amount, bp)
    return Money(floor_div(amount.amount_minor * bp, BASIS_POINTS_PER_UNIT), amount.currency)
