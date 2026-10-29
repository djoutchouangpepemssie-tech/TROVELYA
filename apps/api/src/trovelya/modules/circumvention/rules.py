"""Detection and masking of contact details (section 8.16, plan P2-T05a, Q12, Q30, Q31).

Each rule runs on the normalized text and reports the original passage with a confidence. A
passage of confidence `MASK_AT` or more is masked and the detection confirmed automatically;
below, it is only queued for review: a run of eight digits, digits after « ISBN », « réf. »,
« n° de série » or « facture », a generic payment word, a payment app named with no payment
around (« Lydia » is a first name too), a social network named. The base rule of 8.16
(eight digits or more, `@`, `whats?app`, `lydia`, `paypal`, `telegram`, `z[ée]ro six`, `iban`)
is covered by the rules below.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence

from trovelya.modules.circumvention.models import Detection, Signal
from trovelya.modules.circumvention.normalize import Normalized, normalize

MASK = "••• coordonnées masquées pour ta sécurité"
MASK_AT = 0.9

# [PARAM circumvention.payment_keywords] of 8.16.
MESSAGING_APPS = (r"whats?\s?app\w*", r"watsap\w*", r"telegram\w*")
PAYMENT_APPS = ("lydia", "paypal", "wero", "revolut", "paylib")
PAYMENT_WORDS = ("iban", "rib", "virement", "especes", "cash")
SOCIAL_NETWORKS = ("insta", "instagram", "snapchat", "tiktok", "facebook", "fb")
MAIL_PROVIDERS = ("gmail", "hotmail", "outlook", "yahoo", "icloud", "protonmail", "laposte")
OWN_DOMAINS = ("trovelya.com", "trovelya.fr")
# Digits after these words are a reference, a serial or an invoice: queued, never masked.
REFERENCE_WORDS = r"(?:isbn|ean|ref|reference|sn|serie|n°|no|numero|modele|facture|commande)"

_SEP = r"[\s.,;:_*+()\-/\u2013\u2014·|]{0,3}+"
_DIGITS_RE = re.compile(rf"(?:\+|(?<!\d)00)?\d(?:{_SEP}\d)" + "{7,}")
_FR_PHONE_RE = re.compile(r"0[1-9]\d{8}|(?:33|0033)0?[1-9]\d{8}")
_REFERENCE_RE = re.compile(rf"(?<![a-z]){REFERENCE_WORDS}(?![a-z])[^a-z]{{0,6}}$")
_EMAIL_RE = re.compile(
    r"(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}+\s*@\s*(?:[a-z0-9-]{1,63}\.){1,8}[a-z]{2,24}\b"
)
_ADDRESS_RE = re.compile(r"(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}+\s*@\s*[a-z][a-z0-9-]{1,62}")
_HANDLE_RE = re.compile(r"(?<![a-z0-9._%+-])@[a-z_][a-z0-9_.]{1,29}")
_LINK_RE = re.compile(
    r"https?://\S{1,2000}|www\.\S{1,2000}"
    r"|(?<![a-z0-9.-])(?:[a-z0-9-]{1,63}\.){1,8}"
    r"(?:com|fr|net|org|io|be|eu|info|biz|lu|ch|de)\b(?:/\S{0,2000})?"
)
# An IBAN in one block, or in groups of four after its country and check digits.
_IBAN_RE = re.compile(
    r"(?<![a-z0-9])[a-z]{2}(?:\d{2}[a-z0-9]{11,30}"
    r"|[\s.\-]?\d{2}(?:[\s.\-][a-z0-9]{4}){2,7}(?:[\s.\-][a-z0-9]{1,4})?)(?![a-z0-9])"
)
_PAYING_RE = re.compile(r"pa[iy]|regl|€|euro|rembours|envoi|vir")


def _words(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])")


_MESSAGING_RE = re.compile(r"(?<![a-z])(?:" + "|".join(MESSAGING_APPS) + ")")
_PAYMENT_APPS_RE = _words(PAYMENT_APPS)
_PAYMENT_WORDS_RE = _words(PAYMENT_WORDS)
_NETWORKS_RE = _words(SOCIAL_NETWORKS)
_PROVIDERS_RE = _words(MAIL_PROVIDERS)


def iban_valid(iban: str) -> bool:
    """ISO 13616: 15 to 34 characters, check digits by modulo 97."""
    compact = re.sub(r"[\s.\-]", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


class _Finder:
    """Detections on one text: passages of the original, combining marks that follow
    included, so masking leaves no accent hanging on the mask."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.norm: Normalized = normalize(text)

    def at(self, signal: Signal, start: int, end: int, confidence: float) -> Detection:
        first, last = self.norm.span(start, end)
        while last < len(self.text) and unicodedata.combining(self.text[last]):
            last += 1
        return Detection(signal, first, last, self.text[first:last], confidence)

    def all(self, pattern: re.Pattern[str], signal: Signal, confidence: float) -> list[Detection]:
        return [
            self.at(signal, m.start(), m.end(), confidence)
            for m in pattern.finditer(self.norm.text)
        ]

    def numbers(self) -> list[Detection]:
        found: list[Detection] = []
        for m in _DIGITS_RE.finditer(self.norm.text):
            digits = re.sub(r"\D", "", m.group())
            reference = _REFERENCE_RE.search(self.norm.text[max(0, m.start() - 24) : m.start()])
            international = m.group().startswith("+") or digits.startswith("00")
            if reference:
                found.append(self.at("obfuscated_number", m.start(), m.end(), 0.5))
            elif _FR_PHONE_RE.fullmatch(digits) or (international and 9 <= len(digits) <= 15):
                found.append(self.at("phone", m.start(), m.end(), 0.95))
            else:  # Q31: nine digits or more masked, a run of eight only queued
                confidence = 0.9 if len(digits) >= 9 else 0.5
                found.append(self.at("obfuscated_number", m.start(), m.end(), confidence))
        return found

    def ibans(self) -> list[Detection]:
        found: list[Detection] = []
        for m in _IBAN_RE.finditer(self.norm.text):
            bban = re.sub(r"[\s.\-]", "", m.group())[4:]
            if sum(c.isdigit() for c in bban) < 10 or sum(c.isalpha() for c in bban) > 6:
                continue
            confidence = 0.99 if iban_valid(m.group()) else 0.9  # a mistyped IBAN still is one
            found.append(self.at("iban", m.start(), m.end(), confidence))
        return found

    def links(self) -> list[Detection]:
        found: list[Detection] = []
        for m in _LINK_RE.finditer(self.norm.text):
            detection = self.at("external_link", m.start(), m.end(), 0.9)
            bare = not m.group().startswith(("http", "www."))
            if bare and detection.excerpt != detection.excerpt.lower():
                continue  # « état.Me » is two sentences, not a site
            host = re.sub(r"^(?:https?://)?(?:www\.)?", "", m.group()).split("/")[0]
            if not any(host == own or host.endswith("." + own) for own in OWN_DOMAINS):
                found.append(detection)
        return found

    def payment_apps(self) -> list[Detection]:
        found: list[Detection] = []
        for m in _PAYMENT_APPS_RE.finditer(self.norm.text):
            around = self.norm.text[max(0, m.start() - 40) : m.end() + 40]
            confidence = 0.9 if _PAYING_RE.search(around) else 0.6
            found.append(self.at("payment_app", m.start(), m.end(), confidence))
        return found


def _covered(inner: Detection, outer: Detection) -> bool:
    return (
        inner is not outer
        and outer.start <= inner.start
        and inner.end <= outer.end
        and outer.confidence >= inner.confidence
    )


def detect(text: str) -> list[Detection]:
    """Every passage of `text` that looks like contact details or an off-platform payment, in
    the order of the text; a passage inside a surer one (the domain of an address) is left out."""
    f = _Finder(text)
    found = [
        *f.numbers(),
        *f.ibans(),
        *f.all(_EMAIL_RE, "email", 0.95),
        *f.all(_ADDRESS_RE, "email", 0.9),
        *f.all(_PROVIDERS_RE, "email", 0.9),
        *f.all(_HANDLE_RE, "social_handle", 0.9),
        *f.links(),
        *f.all(_MESSAGING_RE, "payment_app", 0.9),
        *f.payment_apps(),
        *f.all(_PAYMENT_WORDS_RE, "payment_app", 0.6),
        *f.all(_NETWORKS_RE, "social_handle", 0.7),
    ]
    kept = [d for d in found if not any(_covered(d, other) for other in found)]
    return sorted(set(kept), key=lambda d: (d.start, -d.end))


def mask(text: str, detections: Sequence[Detection]) -> str:
    """`text` with each passage of confidence `MASK_AT` or more replaced by `MASK`, passages
    that overlap or touch masked once; the rest of the text as it was."""
    spans = sorted((d.start, d.end) for d in detections if d.confidence >= MASK_AT)
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out: list[str] = []
    last = 0
    for start, end in merged:
        out.append(text[last:start])
        out.append(MASK)
        last = end
    out.append(text[last:])
    return "".join(out)
