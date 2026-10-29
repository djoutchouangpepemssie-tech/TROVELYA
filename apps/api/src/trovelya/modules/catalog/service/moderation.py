"""The moderation of a listing put online (section 8.16, 8.17, plan P2-T05b, Q12, Q32, Q33,
Q34), in this order:

1. prohibited items: `prohibited` reads the title and the description against
   `seed/prohibited.yaml` (a term without ambiguity refuses the listing with its reason, an
   ambiguous one sends it to review, known innocent phrases are taken out first);
2. a category always checked by a human (`is_restricted`) sends it to review;
3. the photos (P2-T05b2, Q38): a score of the classifier past `moderation.image_thresholds`
   refuses the listing or sends it to review; a photo unclassified (no classifier configured,
   or it failed) or already published by another member sends it to review;
4. contact details are masked in the listing itself, recorded, and the seller reminded.
Never commits.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.service.seed import read_seed_file
from trovelya.modules.circumvention.service import MASK, screen
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import Clock

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


RESTRICTED = "restricted_category"
_OTHER_LABELS = {
    RESTRICTED: "Catégorie vérifiée par un humain",
    "image_nudity": "Image : nudité",
    "image_violence": "Image : violence",
    "image_weapons": "Image : armes",
    "image_drugs": "Image : drogue",
    "image_unchecked": "Image à vérifier par un humain",
    "duplicate_image": "Photo déjà publiée par un autre membre",
}


def _combined(*verdicts: Verdict) -> Verdict:
    """The strictest outcome, with the reasons that lead to it (each once, in order)."""
    for outcome in ("refused", "review"):
        reasons = [r for v in verdicts if v.outcome == outcome for r in v.reasons]
        if reasons:
            return Verdict(outcome, tuple(dict.fromkeys(reasons)))
    return Verdict("online")


def photos_verdict(photos: list[dict[str, Any]], thresholds: dict[str, float]) -> Verdict:
    """Q38: refused past `refuse`, reviewed past `review`, unclassified or another member's
    photo reviewed; the classifier's categories become `image_<category>` reasons."""
    refused: list[str] = []
    reviewed: list[str] = []
    for photo in photos:
        classification: dict[str, Any] = photo.get("classification") or {}
        scores: dict[str, float] | None = classification.get("scores")
        if scores is None:
            reviewed.append("image_unchecked")
        for category, score in (scores or {}).items():
            if score >= thresholds["refuse"]:
                refused.append(f"image_{category}")
            elif score >= thresholds["review"]:
                reviewed.append(f"image_{category}")
        if photo.get("duplicate_of"):
            reviewed.append("duplicate_image")
    return _combined(Verdict("refused", tuple(refused)), Verdict("review", tuple(reviewed)))


NOTICE = (
    "Pour ta sécurité, les coordonnées ont été masquées : échange avec l'acheteur par la "
    "messagerie TROVÉLYA, c'est elle qui protège ton paiement et ta vente."
)
_LIMITS = {"title": 120, "description": 5000}


def label(code: str) -> str:
    """The French label of a reason code."""
    return PROHIBITED.labels.get(code) or _OTHER_LABELS[code]


def _fit(text: str, limit: int) -> str:
    """A masked text longer than its column allows is cut before a mask it would split."""
    if len(text) <= limit:
        return text
    cut = limit - 1
    for mask in re.finditer(re.escape(MASK), text):
        if mask.start() < cut < mask.end():
            cut = mask.start()
    return text[:cut].rstrip() + "…"


@dataclass(frozen=True, slots=True)
class Moderated:
    verdict: Verdict
    notice: str | None = None  # the reminder when contact details were masked


class Moderation:
    """The moderation of P2-T05b1 (text); the images join it in T05b2."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def moderate(
        self, db: AsyncSession, *, listing_id: UUID, seller_id: UUID, clock: Clock
    ) -> Moderated:
        subject = await repository.moderation_subject(db, listing_id)
        restricted = Verdict("review", (RESTRICTED,) if subject.is_restricted else ())
        photos = await listing_photos.photo_moderation(
            db, await repository.listing_media_ids(db, listing_id)
        )
        thresholds = await repository.setting_json(db, "moderation.image_thresholds")
        verdict = _combined(
            prohibited(subject.title, subject.description),
            restricted,
            photos_verdict(photos, thresholds),
        )
        # Masked even when refused: an accepted appeal puts the listing back as it is.
        shown = {
            field: await screen(
                db,
                user_id=seller_id,
                source_type="listing",
                source_id=listing_id,
                text=getattr(subject, field),
                settings=self.settings,
                clock=clock,
                part=field,
            )
            for field in _LIMITS
        }
        if all(shown[field] == getattr(subject, field) for field in _LIMITS):
            return Moderated(verdict)
        fitted = {field: _fit(value, _LIMITS[field]) for field, value in shown.items()}
        await repository.set_listing_text(db, listing_id, **fitted)
        return Moderated(verdict, None if verdict.outcome == "refused" else NOTICE)
