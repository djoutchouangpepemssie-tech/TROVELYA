"""Detection and masking of contact details (section 8.16, plan Q12, Q30, Q31).

Each rule runs on the normalized text and reports the original passage with a confidence: from
`MASK_AT`, masked and confirmed automatically; below, only queued for review. Covers the base
rule of 8.16 (eight digits or more, `@`, `whats?app`, `lydia`, `paypal`, `telegram`, `iban`).
"""

import re
from collections.abc import Iterable, Sequence

from trovelya.modules.circumvention.models import Detection, Signal
from trovelya.modules.circumvention.normalize import Normalized, invisible, normalize

MASK = "••• coordonnées masquées pour ta sécurité"
MASK_AT = 0.9

# [PARAM circumvention.payment_keywords] of 8.16.
MESSAGING = (
    r"wh?at['\u2019]?s?\s?ap{1,2}\w*",
    r"wh?atsap\w*",
    r"wh?ats(?![a-z])",
    r"wts?p(?![a-z])",
    r"wsp(?![a-z])",
    r"te[l1i]egram(?!mes?(?![a-z]))\w*",
)
PAYMENT_APPS = ("lydia", "paypal", "wero", "revolut", "paylib")
PAYMENT_WORDS = ("iban", "rib", "virement", "especes", "cash")
SOCIAL_NETWORKS = ("insta", "instagram", "snapchat", "tiktok", "facebook", "fb", "snap")
MAIL_PROVIDERS = ("gmail", "hotmail", "outlook", "yahoo", "icloud", "protonmail", "laposte")
OWN_DOMAINS = ("trovelya.com", "trovelya.fr")
# Digits after these words are a reference, a serial or an invoice: queued, never masked.
REFERENCE_WORDS = (
    r"(?:isbn|ean|ref|reference|sn|serie|modele|facture|commande|siret|siren|tva|lot|code)"
)
# A run followed by a unit is a measure (« 75 cl », « 3000 mah »): queued, never masked.
UNITS = r"(?:mm|cm|m|km|cl|ml|l|g|kg|mah|w|v|go|to|mo|cm3|cc|ch|kw)"

# Separators inside a run: anything but a letter, a digit or « @ »; a comma or a semicolon
# followed by a space ends a list item instead (« 2015, 125 000 km »).
_SEP = r"(?:[^a-z0-9@§,;]|[,;](?!\s)){0,4}+"
_LIST_SEP = r"(?:[^a-z0-9@§]){0,4}+"
_RUN_RE = re.compile(rf"(?:\+|(?<!\d)00)?\d(?:{_LIST_SEP}\d)" + "{7,}")
_ITEM_RE = re.compile(rf"\d(?:{_SEP}\d)*")
_FR_PHONE_RE = re.compile(r"0[1-9]\d{8}|(?:33|0033)0?[1-9]\d{8}")
_MOBILE_RE = re.compile(r"0[67]\d{8}|(?:33|0033)0?[67]\d{8}")
_REFERENCE_RE = re.compile(
    rf"(?<![a-z]){REFERENCE_WORDS}(?![a-z])\.?(?:\s+[a-z]{{1,12}}){{0,2}}[^a-z]{{0,6}}$"
)
_UNIT_RE = re.compile(rf"^\s*{UNITS}(?![a-z])")
_YEAR_RE = re.compile(r"(?:19|20)\d\d")
_EMAIL_RE = re.compile(
    r"(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}+\s*@\s*(?:[a-z0-9-]{1,63}\.){1,8}[a-z]{2,24}\b"
)
_ADDRESS_RE = re.compile(r"(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}+\s*@\s*[a-z][a-z0-9-]{1,62}")
_AT_SIGN_RE = re.compile(r"@")
_HANDLE_RE = re.compile(r"(?<![a-z0-9._%+-])@[a-z_][a-z0-9_.]{1,29}")
_LINK_RE = re.compile(
    r"https?://\S{1,2000}|www\.\S{1,2000}"
    r"|(?<![a-z0-9.-])(?:[a-z0-9-]{1,63}\.){1,8}[a-z]{2,24}/\S{1,2000}"
    r"|(?<![a-z0-9.-])(?:[a-z0-9-]{1,63}\.){1,8}(?:com|fr|net|org|io|be|eu|info|biz|lu|ch|de"
    r"|me|ly|co|ee|gg|shop|store|app|xyz)\b"
)
_IBAN_RE = re.compile(
    r"(?<![a-z0-9])[a-z]{2}(?:\d{2}[a-z0-9]{11,30}"
    r"|[\s.\-/_]?\d{2}(?:[\s.\-/_][a-z0-9]{1,11}){2,8})(?![a-z0-9])"
)
_PAYING_RE = re.compile(
    r"(?<![a-z])(?:pai(?:e|ement)\w*|pay(?:er|ez)|regl\w*|rembours\w*|virement\w*"
    r"|transfert\w*|accept\w*)(?![a-z])"
)


def _words(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])")


_MESSAGING_RE = re.compile(r"(?<![a-z])(?:" + "|".join(MESSAGING) + ")")
_PAYMENT_APPS_RE = _words(PAYMENT_APPS)
_PAYMENT_WORDS_RE = _words(PAYMENT_WORDS)
_NETWORKS_RE = re.compile(
    r"(?<![a-z])(?<!polaroid )(?:" + "|".join(SOCIAL_NETWORKS) + r")(?![a-z])"
)
# A mail provider named, with the word before it (the name of the address).
_PROVIDERS_RE = re.compile(
    r"(?<![a-z0-9._%+-])(?:[a-z0-9._%+-]{1,64}\s+)?(?:" + "|".join(MAIL_PROVIDERS) + r")(?![a-z])"
)


def iban_valid(iban: str) -> bool:
    """ISO 13616: 15 to 34 characters, check digits by modulo 97."""
    compact = re.sub(r"[\s.\-/_]", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def isbn10_valid(digits: str) -> bool:
    """An ISBN-10 by its check digit (a final X stands for 10, not handled: digits only)."""
    if len(digits) != 10:
        return False
    return sum((10 - i) * int(d) for i, d in enumerate(digits)) % 11 == 0


def ean_valid(digits: str) -> bool:
    """An EAN-13 or ISBN-13 (a product's barcode, a book) by its check digit."""
    if len(digits) != 13:
        return False
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == int(digits[12])


class _Finder:
    """Detections on one text: passages of the original, invisible characters that follow
    (an accent, an emoji's keycap) included, so masking leaves nothing hanging on the mask."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.norm: Normalized = normalize(text)

    def at(self, signal: Signal, start: int, end: int, confidence: float) -> Detection:
        first, last = self.norm.span(start, end)
        while last < len(self.text) and invisible(self.text[last]):
            last += 1
        return Detection(signal, first, last, self.text[first:last], confidence)

    def all(self, pattern: re.Pattern[str], signal: Signal, confidence: float) -> list[Detection]:
        found = pattern.finditer(self.norm.text)
        return [self.at(signal, m.start(), m.end(), confidence) for m in found]

    def numbers(self) -> list[Detection]:
        found: list[Detection] = []
        for run in _RUN_RE.finditer(self.norm.text):
            digits = re.sub(r"\D", "", run.group())
            international = run.group().startswith("+") or digits.startswith("00")
            phone = _FR_PHONE_RE.fullmatch(digits) or (international and 9 <= len(digits) <= 15)
            # A mobile number is always one; a fixed-line shape after « réf. », « n° de
            # série »… or a valid ISBN-10 is a reference (« réf. » before a mobile is a trick).
            reference = not _MOBILE_RE.fullmatch(digits) and (
                bool(_REFERENCE_RE.search(self.norm.text[max(0, run.start() - 32) : run.start()]))
                or isbn10_valid(digits)
            )
            if phone and not reference:
                found.append(self.at("phone", run.start(), run.end(), 0.95))
                continue
            # Not a phone number: each item of a list (« 2015, 125 000 km ») on its own.
            for item in _ITEM_RE.finditer(run.group()):
                start, end = run.start() + item.start(), run.start() + item.end()
                confidence = self._run_confidence(item.group(), start, end)
                if confidence:
                    found.append(self.at("obfuscated_number", start, end, confidence))
        return found

    def _run_confidence(self, run: str, start: int, end: int) -> float:
        """Q31: nine digits or more masked, eight queued; a reference, a barcode, a measure
        or a list of years queued or let go."""
        digits = re.sub(r"\D", "", run)
        if len(digits) < 8:
            return 0
        groups = re.findall(r"\d+", run)
        if all(len(g) == 4 and _YEAR_RE.fullmatch(g) for g in groups):
            return 0  # « 1965 1972 1978 1981 »
        before = self.norm.text[max(0, start - 32) : start]
        after = self.norm.text[end : end + 8]
        barcode = ean_valid(digits) or isbn10_valid(digits)
        if _REFERENCE_RE.search(before) or _UNIT_RE.search(after) or barcode:
            return 0.5
        return 0.9 if len(digits) >= 9 else 0.5

    def ibans(self) -> list[Detection]:
        found: list[Detection] = []
        for m in _IBAN_RE.finditer(self.norm.text):
            bban = re.sub(r"[\s.\-/_]", "", m.group())[4:]
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
        """Masked with a payment word around (« payer par PayPal »), else queued: « Lydia » is
        a first name and a brand too."""
        found: list[Detection] = []
        for m in _PAYMENT_APPS_RE.finditer(self.norm.text):
            around = self.norm.text[max(0, m.start() - 40) : m.start()]
            around += " " + self.norm.text[m.end() : m.end() + 40]
            confidence = 0.9 if _PAYING_RE.search(around) else 0.6
            found.append(self.at("payment_app", m.start(), m.end(), confidence))
        return found


def _keep(found: list[Detection]) -> list[Detection]:
    """Without duplicates, nor passages inside a surer one (the domain of an address), in the
    order of the text: one sweep, a few confidence levels."""
    ordered = sorted(set(found), key=lambda d: (d.start, -d.end, -d.confidence))
    reach: dict[float, int] = {}  # confidence → furthest end of a passage seen so far
    kept: list[Detection] = []
    for d in ordered:
        if any(level >= d.confidence and end >= d.end for level, end in reach.items()):
            continue
        kept.append(d)
        reach[d.confidence] = max(reach.get(d.confidence, 0), d.end)
    return kept


def detect(text: str) -> list[Detection]:
    """Every passage of `text` that looks like contact details or an off-platform payment."""
    f = _Finder(text)
    return _keep(
        [
            *f.numbers(),
            *f.ibans(),
            *f.all(_EMAIL_RE, "email", 0.95),
            *f.all(_ADDRESS_RE, "email", 0.9),
            *f.all(_PROVIDERS_RE, "email", 0.9),
            *f.all(_AT_SIGN_RE, "email", 0.5),
            *f.all(_HANDLE_RE, "social_handle", 0.9),
            *f.links(),
            *f.all(_MESSAGING_RE, "payment_app", 0.9),
            *f.payment_apps(),
            *f.all(_PAYMENT_WORDS_RE, "payment_app", 0.6),
            *f.all(_NETWORKS_RE, "social_handle", 0.7),
        ]
    )


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
