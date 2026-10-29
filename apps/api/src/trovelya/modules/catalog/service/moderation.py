"""Prohibited items in a listing's text (section 8.17, plan P2-T05b1a, Q33, Q34).

`prohibited` reads the title and the description against `seed/prohibited.yaml`: a term
without ambiguity refuses the listing with its reason, an ambiguous one sends it to review,
known innocent phrases are taken out first. Pure: no database. The moderation of a listing
put online (restricted categories, contact details) builds on it in P2-T05b1b.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from trovelya.modules.catalog.service.seed import read_seed_file

Outcome = Literal["online", "review", "refused"]

# A digit between two letters reads as the letter it looks like (« r0lex », « x4nax »), as
# do « @ » and « $ » in a word (« vodk@ »); letters spaced out are put together (« g l o c k »).
_LOOK_ALIKES = str.maketrans("013457", "oieast")
_LOOK_ALIKE_RE = re.compile(r"(?<=[a-z])[013457]+(?=[a-z])")
_SYMBOLS = str.maketrans({"@": "a", "$": "s", "œ": "oe", "æ": "ae", "ß": "ss"})
_SPACED_RE = re.compile(r"(?<![a-z0-9])(?:[a-z] ){3,}[a-z](?![a-z0-9])")


def normalize(text: str) -> str:
    """Lower case, without accents nor punctuation, look-alikes read as letters, words
    separated by one space: « Défense d'Éléphant » → « defense d elephant »."""
    lowered = unicodedata.normalize("NFKD", text.lower().translate(_SYMBOLS))
    plain = "".join(c for c in lowered if not unicodedata.combining(c))
    plain = _LOOK_ALIKE_RE.sub(lambda m: m.group().translate(_LOOK_ALIKES), plain)
    words = " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())
    return _SPACED_RE.sub(lambda m: m.group().replace(" ", ""), words)


def _word(word: str) -> str:
    """One word of a term; `*` at its end accepts any end of word."""
    stem = re.escape(normalize(word.removesuffix("*")))
    return stem + (r"[a-z0-9]*" if word.endswith("*") else "")


_TOKEN_RE = re.compile(r"\([^)]*\)\??|\S+")


def _term(term: str) -> str:
    """A term of the list: words, `(a|b c)` one of them, `~` any one word, `#` a number, `?`
    after a word or a group: optional."""
    out = ""
    for piece in _TOKEN_RE.findall(term):
        optional = piece.endswith("?")
        piece = piece.removesuffix("?")
        if piece.startswith("(") and piece.endswith(")"):
            alternatives = (" ".join(map(_word, a.split())) for a in piece[1:-1].split("|"))
            part = "(?:" + "|".join(alternatives) + ")"
        elif piece == "~":
            part = "[a-z0-9]+"
        elif piece == "#":
            part = "[0-9]+"
        else:
            part = _word(piece)
        sep = " " if out else ""
        out += f"(?:{sep}{part})?" if optional else sep + part
    return out


def _pattern(terms: list[str]) -> re.Pattern[str] | None:
    """Whole words only."""
    if not terms:
        return None
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(map(_term, terms)) + r")(?![a-z0-9])")


@dataclass(frozen=True, slots=True)
class _Reason:
    refuse: re.Pattern[str] | None
    review: re.Pattern[str] | None


@dataclass(frozen=True, slots=True)
class Prohibited:
    """The list of 8.17: reasons in the order of the file, their labels, the words that
    change the object and the innocent phrases."""

    reasons: dict[str, _Reason]
    labels: dict[str, str]
    unless: re.Pattern[str] | None
    exceptions: re.Pattern[str] | None

    @classmethod
    def load(cls, document: dict[str, Any]) -> "Prohibited":
        reasons = {
            code: _Reason(_pattern(entry.get("refuse") or []), _pattern(entry.get("review") or []))
            for code, entry in document["reasons"].items()
        }
        labels = {code: entry["label"] for code, entry in document["reasons"].items()}
        return cls(
            reasons,
            labels,
            _pattern(document.get("unless") or []),
            _pattern(document.get("except") or []),
        )


PROHIBITED = Prohibited.load(read_seed_file("prohibited.yaml"))


@dataclass(frozen=True, slots=True)
class Verdict:
    """Where the listing goes, and why (reason codes, in the order of the list)."""

    outcome: Outcome
    reasons: tuple[str, ...] = ()


def prohibited(title: str, description: str, *, terms: Prohibited = PROHIBITED) -> Verdict:
    """Q34: refused when a term without ambiguity is found, unless another word changes the
    object (« étui », « vide », « chocolat »…: then reviewed); reviewed for an ambiguous term;
    else online."""
    text = normalize(f"{title} {description}")
    if terms.exceptions is not None:
        text = terms.exceptions.sub(" ", text)
    refused: list[str] = []
    reviewed: list[str] = []
    for code, reason in terms.reasons.items():
        if reason.refuse is not None and reason.refuse.search(text):
            rest = reason.refuse.sub(" ", text)  # the words around the term, not its own
            changed = terms.unless is not None and terms.unless.search(rest)
            (reviewed if changed else refused).append(code)
        elif reason.review is not None and reason.review.search(text):
            reviewed.append(code)
    if refused:
        return Verdict("refused", tuple(refused))
    if reviewed:
        return Verdict("review", tuple(reviewed))
    return Verdict("online")
