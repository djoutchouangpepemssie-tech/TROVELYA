"""Normalisation before detection (section 8.16): lower case, no accents nor invisible
characters, look-alike letters and digits of any script made Latin and ASCII, numbers in words
made digits (« zéro six douze » → « 0 6 12 »), « O6 l2 » among digits made « 06 12 », obfuscated
« @ » and « . » put back, dates kept as one block. Every character of the result keeps the span
of the original it comes from, so a detection points to the very passage written.
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


# Look-alike letters (Unicode confusables, UTS #39) most used to dodge a keyword.
_CONFUSABLES = str.maketrans(
    # Cyrillic a b e k m h o p c t y x i j s d
    "\u0430\u0432\u0435\u043a\u043c\u043d\u043e\u0440\u0441\u0442\u0443\u0445"
    "\u0456\u0458\u0455\u0501"
    # Greek a b e i k v o p t u x
    "\u03b1\u03b2\u03b5\u03b9\u03ba\u03bd\u03bf\u03c1\u03c4\u03c5\u03c7",
    "abekmhopctyxijsdabeikvoptux",
)


def invisible(char: str) -> bool:
    """Invisible or decorative: format characters (zero width, soft hyphen…), combining marks,
    variation selectors and the keycap mark of « 0️⃣ »."""
    return (
        unicodedata.category(char) == "Cf"
        or unicodedata.combining(char) != 0
        or "\ufe00" <= char <= "\ufe0f"
        or char == "\u20e3"
    )


def _chars(text: str) -> tuple[list[str], list[Span]]:
    chars: list[str] = []
    origin: list[Span] = []
    for i, char in enumerate(text):
        decomposed = unicodedata.normalize("NFKD", char.lower())
        if char in _POWERS and i and text[i - 1].isalpha():
            decomposed = "§"  # « m² », « cm³ »: a unit, not a digit
        elif len(decomposed) > 4:  # a ligature of a whole phrase (« ﷺ »): not worth expanding
            decomposed = char.lower()
        for part in decomposed:
            if invisible(part):
                continue
            if part.isdecimal() and not part.isascii():
                part = str(unicodedata.decimal(part))
            chars.append(part.translate(_CONFUSABLES))
            origin.append((i, i + 1))
    return chars, origin


_POWERS = "\u00b2\u00b3"
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
_NUMBER_WORD = "|".join(
    name.replace("-", r"[\s-]+") for name in sorted(_NUMBERS, key=len, reverse=True)
)
# Number words written apart or glued (« zérosix »), never inside a longer word (« septembre »).
_NUMBERS_RE = re.compile(rf"(?<![a-z])(?:{_NUMBER_WORD})(?:(?:{_NUMBER_WORD})|(?=\d))*(?![a-z])")
_ONE_NUMBER_RE = re.compile(_NUMBER_WORD)
# A date stands alone: « 06.12.34.56.78 » is no date but a phone number.
_DATE_RE = re.compile(
    r"(?<!\d)(?<!\d[/.\-])\d{1,2}[/.\-]\d{1,2}[/.\-](?:\d{4}|\d{2})(?!\d)(?![/.\-]\d)"
)
# A month of a year (« MEC 07/2016 ») stands alone too.
_MONTH_YEAR_RE = re.compile(r"(?<![\d/.\-])(?:0?[1-9]|1[0-2])/(?:19|20)\d\d(?![\d/.\-])")
# « O6 l2 »: a letter o or l right before a digit reads as one (never « i7 » or « 4l »).
_DIGIT_LETTERS_RE = re.compile(r"(?<![a-z])[ol](?=\d)|(?<=\d)[ol](?=\d)")
# « j e a n », « 0 6 1 2 »: single characters spaced out are put back together.
_SPACED_RE = re.compile(r"(?<![a-z0-9])[a-z0-9](?:[ .][a-z0-9]){3,}+(?![a-z0-9])")
_TLD = r"(?:com|fr|net|org|eu|be|de|it|es|lu|ch|io|info)\b"
# Mail providers only: « chez Orange », « chez Free » is where a phone or a box was bought.
_PROVIDERS = r"(?:gmail|hotmail|outlook|yahoo|icloud|protonmail)\b"
# Each starts where no white space precedes, so a long run of spaces is read once.
_AT_RE = re.compile(
    r"(?<!\s)\s*(?:[\[(]\s*(?:at|a|@|arobase)\s*[\])]|(?<![a-z])arobase(?![a-z])"
    rf"|(?<![a-z])at(?=\s+[a-z0-9-]+\s*(?:\.|dot\b|point\b)\s*{_TLD})"
    rf"|(?<![a-z])chez(?=\s+{_PROVIDERS}))\s*"
)
# A plain « . » between spaces ends a sentence (« état. de plus »), but before a common
# extension: then only it reads as the dot of a domain.
_DOT_RE = re.compile(
    r"(?<!\s)(?:\s*(?:[\[(]\s*(?:dot|\.|point)\s*[\])]|(?<![a-z])(?:dot|point)(?![a-z]))"
    rf"\s*(?={_TLD})|\s*\.\s*(?=(?:com|fr|net|org)\b))"
)
_NAME_DOT_RE = re.compile(r"(?<!\s)\s+(?:point|dot)\s+(?=[a-z0-9-]+\s*@)")


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


def _numbers(words: str) -> str:
    """« zéro six » → « 0 6 », « zérosix » → « 06 »: what separated the words stays."""
    return _ONE_NUMBER_RE.sub(lambda m: str(_NUMBERS[re.sub(r"[\s-]+", "-", m.group())]), words)


def normalize(text: str) -> Normalized:
    chars, origin = _chars(text)
    norm = Normalized("".join(chars), origin)
    norm = _sub(norm, _DATE_RE, lambda _: "§")
    norm = _sub(norm, _MONTH_YEAR_RE, lambda _: "§")
    norm = _sub(norm, _NUMBERS_RE, _numbers)
    norm = _sub(norm, _DIGIT_LETTERS_RE, lambda c: "0" if c == "o" else "1")
    norm = _sub(norm, _SPACED_RE, lambda run: re.sub(r"[ .]", "", run))
    norm = _sub(norm, _AT_RE, lambda _: "@")
    norm = _sub(norm, _NAME_DOT_RE, lambda _: ".")
    return _sub(norm, _DOT_RE, lambda _: ".")
