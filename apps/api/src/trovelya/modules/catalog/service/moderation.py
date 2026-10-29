"""The moderation of a listing put online (section 8.17, plan P2-T05b, Q32, Q33, Q34).

`prohibited` reads the title and the description against `seed/prohibited.yaml`: a term
without ambiguity refuses the listing with its reason, an ambiguous one sends it to review,
known innocent phrases are taken out first. Pure: no database.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from trovelya.modules.catalog.service.seed import read_seed_file

Outcome = Literal["online", "review", "refused"]

# A digit between two letters reads as the letter it looks like (« r0lex », « x4nax »).
_LOOK_ALIKES = str.maketrans("013457", "oieast")
_LOOK_ALIKE_RE = re.compile(r"(?<=[a-z])[013457]+(?=[a-z])")
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae", "ß": "ss"})


def normalize(text: str) -> str:
    """Lower case, without accents nor punctuation, look-alike digits read as letters, words
    separated by one space: « Défense d'Éléphant » → « defense d elephant »."""
    lowered = unicodedata.normalize("NFKD", text.lower().translate(_LIGATURES))
    plain = "".join(c for c in lowered if not unicodedata.combining(c))
    plain = _LOOK_ALIKE_RE.sub(lambda m: m.group().translate(_LOOK_ALIKES), plain)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _pattern(terms: list[str]) -> re.Pattern[str] | None:
    """Whole words; `*` at the end of a term accepts any end of word."""
    if not terms:
        return None
    parts = [
        re.escape(normalize(t.removesuffix("*"))).replace(r"\ ", " ")
        + (r"[a-z0-9]*" if t.endswith("*") else "")
        for t in terms
    ]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])")


@dataclass(frozen=True, slots=True)
class _Reason:
    refuse: re.Pattern[str] | None
    review: re.Pattern[str] | None
    unless: re.Pattern[str] | None


@dataclass(frozen=True, slots=True)
class Prohibited:
    """The list of 8.17: reasons in the order of the file, their labels, the exceptions."""

    reasons: dict[str, _Reason]
    labels: dict[str, str]
    exceptions: re.Pattern[str] | None

    @classmethod
    def load(cls, document: dict[str, Any]) -> "Prohibited":
        reasons = {
            code: _Reason(
                _pattern(entry.get("refuse") or []),
                _pattern(entry.get("review") or []),
                _pattern(entry.get("unless") or []),
            )
            for code, entry in document["reasons"].items()
        }
        labels = {code: entry["label"] for code, entry in document["reasons"].items()}
        return cls(reasons, labels, _pattern(document.get("except") or []))


PROHIBITED = Prohibited.load(read_seed_file("prohibited.yaml"))


@dataclass(frozen=True, slots=True)
class Verdict:
    """Where the listing goes, and why (reason codes, in the order of the list)."""

    outcome: Outcome
    reasons: tuple[str, ...] = ()


def prohibited(title: str, description: str, *, terms: Prohibited = PROHIBITED) -> Verdict:
    """Q34: refused when a term without ambiguity is found (unless a word such as « jouet »
    changes the object: then reviewed), reviewed for an ambiguous term, else online."""
    text = normalize(f"{title} {description}")
    if terms.exceptions is not None:
        text = terms.exceptions.sub(" ", text)
    refused: list[str] = []
    reviewed: list[str] = []
    for code, reason in terms.reasons.items():
        if reason.refuse is not None and reason.refuse.search(text):
            changed = reason.unless is not None and reason.unless.search(text)
            (reviewed if changed else refused).append(code)
        elif reason.review is not None and reason.review.search(text):
            reviewed.append(code)
    if refused:
        return Verdict("refused", tuple(refused))
    if reviewed:
        return Verdict("review", tuple(reviewed))
    return Verdict("online")
