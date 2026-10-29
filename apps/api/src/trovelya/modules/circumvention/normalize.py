"""Normalisation before detection (section 8.16): lower case, no accents, numbers written in
words turned into digits (« zéro six douze » → « 0 6 12 »), obfuscated « @ » and « . » of an
address put back. Every character of the result keeps the span of the original it comes from,
so a detection always points to the very passage the member wrote.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

Span = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Normalized:
    text: str
    origin: list[Span]  # origin[i]: the original span the i-th character comes from

    def span(self, start: int, end: int) -> Span:
        """The original span of the normalized passage `[start, end)`."""
        return self.origin[start][0], self.origin[end - 1][1]


_UNITS = ["zero", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"]
_TEENS = ["dix", "onze", "douze", "treize", "quatorze", "quinze", "seize"]
_TENS = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}


def _number_words() -> dict[str, int]:
    """French numbers 0 to 99 in words, each part joined by « - » (spaces are matched too)."""
    words: dict[str, int] = {name: value for value, name in enumerate(_UNITS)}
    words |= {name: 10 + i for i, name in enumerate(_TEENS)}
    for i, unit in enumerate(["sept", "huit", "neuf"], start=7):
        words[f"dix-{unit}"] = 10 + i
    below_twenty = {value: name for name, value in words.items() if 1 <= value <= 19}
    for tens, name in _TENS.items():
        words[name] = tens
        words[f"{name}-et-un"] = tens + 1
        for unit in range(2, 10):
            words[f"{name}-{_UNITS[unit]}"] = tens + unit
    for value in range(10, 20):  # soixante-dix … soixante-dix-neuf
        words[f"soixante-{below_twenty[value]}"] = 60 + value
    words["soixante-et-onze"] = 71
    for stem in ("quatre-vingt", "quatre-vingts"):
        words[stem] = 80
    for value in range(1, 20):
        words[f"quatre-vingt-{below_twenty[value]}"] = 80 + value
    return words


_NUMBERS = _number_words()
_NUMBER_RE = re.compile(
    r"\b(?:"
    + "|".join(name.replace("-", r"[\s-]+") for name in sorted(_NUMBERS, key=len, reverse=True))
    + r")\b"
)
_AT_RE = re.compile(r"\s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\barobase\b)\s*")
_DOT_RE = re.compile(
    r"\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\bpoint\b)\s*(?=(?:com|fr|net|org|eu|be)\b)"
)


def _sub(norm: Normalized, pattern: re.Pattern[str], repl: Callable[[str], str]) -> Normalized:
    """Replace each match; the characters put in its place come from the whole match."""
    text: list[str] = []
    origin: list[Span] = []
    last = 0
    for m in pattern.finditer(norm.text):
        text.append(norm.text[last : m.start()])
        origin.extend(norm.origin[last : m.start()])
        replacement = repl(m.group())
        text.append(replacement)
        origin.extend([norm.span(m.start(), m.end())] * len(replacement))
        last = m.end()
    text.append(norm.text[last:])
    origin.extend(norm.origin[last:])
    return Normalized("".join(text), origin)


def _number(words: str) -> str:
    value = _NUMBERS[re.sub(r"[\s-]+", "-", words)]
    return str(value) if value >= 10 else f"{value}"


def normalize(text: str) -> Normalized:
    chars: list[str] = []
    origin: list[Span] = []
    for i, char in enumerate(text):
        for part in unicodedata.normalize("NFKD", char.lower()):
            if not unicodedata.combining(part):
                chars.append(part)
                origin.append((i, i + 1))
    norm = Normalized("".join(chars), origin)
    norm = _sub(norm, _NUMBER_RE, _number)
    norm = _sub(norm, _AT_RE, lambda _: "@")
    return _sub(norm, _DOT_RE, lambda _: ".")
