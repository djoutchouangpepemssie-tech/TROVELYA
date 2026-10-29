"""Detection and masking of contact details (section 8.16, plan P2-T05a, Q12).

Each rule runs on the normalized text and reports the original passage with a confidence. A
passage of confidence `MASK_AT` or more is masked and the detection confirmed automatically;
below, it is only queued for review (a run of eight digits that is no phone number, a generic
payment word). The base rule of 8.16 (eight digits or more, `@`, the apps and « iban ») is
covered by the rules below.
"""

import re
from collections.abc import Iterable, Sequence

from trovelya.modules.circumvention.models import Detection, Signal
from trovelya.modules.circumvention.normalize import Normalized, normalize

MASK = "••• coordonnées masquées pour ta sécurité"
MASK_AT = 0.9

# [PARAM circumvention.payment_keywords] of 8.16: names of apps (clear intent, masked) and
# generic words (queued only).
PAYMENT_APPS = ("whatsapp", "whats app", "watsap", "telegram", "lydia", "paypal", "wero", "revolut")
PAYMENT_WORDS = ("iban", "rib", "virement", "especes")
SOCIAL_NETWORKS = ("insta", "instagram", "snap", "snapchat", "tiktok", "facebook")
OWN_DOMAINS = ("trovelya.com", "trovelya.fr")

_DIGITS_RE = re.compile(r"(?:\+|\b00)?\d(?:[\s.\-/]{0,3}\d){7,}")
_PHONE_RE = re.compile(r"(?:0[1-9]\d{8}|(?:33|0033)[1-9]\d{8})")
_EMAIL_RE = re.compile(
    r"[a-z0-9._%+-]+\s*@\s*[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b"
)
_HANDLE_RE = re.compile(r"(?<![a-z0-9._%+-])@[a-z0-9_.]{2,30}")
_LINK_RE = re.compile(
    r"https?://\S+|www\.\S+"
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|fr|net|org|io|be|eu|me|ly|info|biz|co)\b(?:/\S*)?"
)
_IBAN_RE = re.compile(r"\b[a-z]{2}\d{2}(?:\s?[a-z0-9]){11,30}\b")


def _words(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b")


_APPS_RE = _words(PAYMENT_APPS)
_PAYMENT_WORDS_RE = _words(PAYMENT_WORDS)
_NETWORKS_RE = _words(SOCIAL_NETWORKS)


def iban_valid(iban: str) -> bool:
    """ISO 13616: 15 to 34 characters, check digits by modulo 97."""
    compact = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def _found(
    text: str, norm: Normalized, pattern: re.Pattern[str], signal: Signal, confidence: float
) -> list[Detection]:
    found: list[Detection] = []
    for m in pattern.finditer(norm.text):
        start, end = norm.span(m.start(), m.end())
        found.append(Detection(signal, start, end, text[start:end], confidence))
    return found


def _numbers(text: str, norm: Normalized) -> list[Detection]:
    found: list[Detection] = []
    for m in _DIGITS_RE.finditer(norm.text):
        digits = re.sub(r"\D", "", m.group())
        start, end = norm.span(m.start(), m.end())
        if _PHONE_RE.fullmatch(digits):
            found.append(Detection("phone", start, end, text[start:end], 0.95))
        else:
            found.append(Detection("obfuscated_number", start, end, text[start:end], 0.5))
    return found


def _ibans(text: str, norm: Normalized) -> list[Detection]:
    return [d for d in _found(text, norm, _IBAN_RE, "iban", 0.99) if iban_valid(d.excerpt)]


def _links(text: str, norm: Normalized) -> list[Detection]:
    return [
        d
        for d in _found(text, norm, _LINK_RE, "external_link", 0.9)
        if not any(own in d.excerpt.lower() for own in OWN_DOMAINS)
    ]


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
    norm = normalize(text)
    found = [
        *_numbers(text, norm),
        *_ibans(text, norm),
        *_found(text, norm, _EMAIL_RE, "email", 0.95),
        *_found(text, norm, _HANDLE_RE, "social_handle", 0.9),
        *_links(text, norm),
        *_found(text, norm, _APPS_RE, "payment_app", 0.9),
        *_found(text, norm, _PAYMENT_WORDS_RE, "payment_app", 0.6),
        *_found(text, norm, _NETWORKS_RE, "social_handle", 0.7),
    ]
    kept = [d for d in found if not any(_covered(d, other) for other in found)]
    return sorted(set(kept), key=lambda d: (d.start, -d.end))


def mask(text: str, detections: Sequence[Detection]) -> str:
    """`text` with each passage of confidence `MASK_AT` or more replaced by `MASK`, passages
    that overlap masked once; the rest of the text as it was."""
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
