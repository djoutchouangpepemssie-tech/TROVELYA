"""Anti-circumvention value types (section 7.10)."""

from dataclasses import dataclass
from typing import Literal

Signal = Literal[
    "phone",
    "email",
    "iban",
    "payment_app",
    "external_link",
    "social_handle",
    "obfuscated_number",
    "meet_off_app",
]


@dataclass(frozen=True, slots=True)
class Detection:
    """A passage of the original text: `text[start:end] == excerpt`."""

    signal: Signal
    start: int
    end: int
    excerpt: str
    confidence: float
