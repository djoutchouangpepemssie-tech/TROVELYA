"""Detection and masking of contact details (section 8.16, plan Q12, Q30, Q31).

Each rule runs on the normalized text and reports the original passage with a confidence: from
`MASK_AT`, masked and confirmed automatically; below, only queued for review. Covers the base
rule of 8.16 (eight digits or more, `@`, `whats?app`, `lydia`, `paypal`, `telegram`, `iban`).
"""

import re
from collections.abc import Iterable, Sequence
from itertools import pairwise

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
MAIL_PROVIDERS = ("gmail", "hotmail", "outlook", "yahoo", "icloud", "protonmail")
# Named alone, these are software or a service too (« compte iCloud », « Pack Office : Outlook »).
PROVIDERS_NAMED_ALONE = ("gmail", "hotmail", "yahoo", "protonmail")
# After an explicit « @ », operators' mail too.
AT_PROVIDERS = (
    *MAIL_PROVIDERS,
    *("laposte", "orange", "free", "sfr", "wanadoo", "gmx", "aol", "live", "msn", "ymail"),
    *("proton", "neuf", "bbox", "numericable", "aliceadsl", "club-internet"),
)
OWN_DOMAINS = ("trovelya.com", "trovelya.fr")
# Digits after these words are a reference, a serial or an invoice: queued, never masked.
REFERENCE_WORDS = (
    r"(?:isbn|ean|ref|reference|sn|serie|modele|facture|commande|siret|siren|tva|lot|code)"
)
# A run followed by a unit is a measure (« 75 cl », « 3000 mah »): queued, never masked.
UNITS = (
    r"(?:mm|cm|m|km|kms|kilometres?|cl|ml|l|g|kg|mah|w|v|go|to|mo|cm3|cc|ch|kw|kwh|h|heures?"
    r"|€|eur|euros?)"
)
# Lengths of the IBAN of the SEPA countries and of the Maghreb (ISO 13616 registry).
IBAN_LENGTHS = {
    code: int(length)
    for code, length in re.findall(
        r"([a-z]{2})(\d+)",
        "ad24 at20 be16 bg22 ch21 cy28 cz24 de22 dk18 ee20 es24 fi18 fr27 gb22 gi23 gr27 hr21 "
        "hu28 ie22 is26 it27 li21 lt20 lu20 lv21 ma28 mc27 mt31 nl18 no15 pl28 pt25 ro24 se24 "
        "si19 sk24 sm27 tn24 va22",
    )
}

# Separators inside a run: spaces, punctuation and dashes, never the multiplication sign of a
# screen's definition, « € », « % » nor a fraction (« 38 ½ »); a comma or a semicolon followed
# by a space ends a list item instead (« 2015, 125 000 km »).
_SEPARATOR = r"\s.\-_/:()\[\]+*|·~#•'\u2010-\u2015\u2212"
_SEP = rf"(?:[{_SEPARATOR}]|[,;](?!\s)){{0,4}}+"
# A phone number is looked for across any separator (« 06!12!34 », an emoji): only the
# counting of the other digits stops at « € » or the multiplication sign.
_ANY_SEP = r"[^a-z0-9@§]{0,4}+"
_RUN_RE = re.compile(rf"(?:\+|(?<!\d)00)?\d(?:{_ANY_SEP}\d)" + "{7,}")
_GROUP_RE = re.compile(r"\d+")
_LIST_ITEM_SEP_RE = re.compile(r"[,;]\s")
_TIME_RE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")
_FRACTIONS_RE = re.compile(r"(?:\d{1,3}\s+)?\d{1,2}/\d{1,2}(?:\s+(?:\d{1,3}\s+)?\d{1,2}/\d{1,2})+")
_LONE_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d\d(?!\d)")
_ITEM_RE = re.compile(rf"\d(?:{_SEP}\d)*")
_FR_PHONE_RE = re.compile(r"0[1-9]\d{8}|(?:33|0033)0?[1-9]\d{8}")
_MOBILE_RE = re.compile(r"0[67]\d{8}|(?:33|0033)0?[67]\d{8}")
_REFERENCE_RE = re.compile(
    rf"(?<![a-z]){REFERENCE_WORDS}(?![a-z])\.?(?:[\s']+[a-z]{{1,12}}){{0,2}}[^a-z]{{0,8}}$"
)
# « n° » before digits that are no phone number: an invoice, a serial (« N° 123456789 »).
_NUMBER_SIGN_RE = re.compile(r"(?<![a-z])(?:n°|no)\s*[^a-z]{0,4}$")
_UNIT_RE = re.compile(rf"^\s*{UNITS}(?![a-z'\u2019])")
_YEAR_RE = re.compile(r"(?:19|20)\d\d")
_EMAIL_RE = re.compile(
    r"(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}+\s*@\s*(?:[a-z0-9-]{1,63}\.){1,8}[a-z]{2,24}\b"
)
# Without its domain: « jean@gmail »; spaced out, only before a provider (« Jean @ la
# boutique » is no address).
_ADDRESS_RE = re.compile(r"(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}+@[a-z][a-z0-9-]{1,62}")
_SPACED_ADDRESS_RE = re.compile(
    r"(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}+\s*@\s*(?:" + "|".join(AT_PROVIDERS) + r")(?![a-z])"
)
_AT_SIGN_RE = re.compile(r"@")
_HANDLE_RE = re.compile(r"(?<![a-z0-9._%+-])@[a-z_][a-z0-9_.]{1,29}")
_TLDS = "com|fr|net|org|io|be|eu|info|biz|lu|ch|de|me|ly|co|ee|gg|shop|store|app|xyz"
# A bare domain never ends in « de » or « eu » (« servi.de couleur »); one with a path, only
# in a known extension (« bleu.vert/rouge » is no site).
_BARE_TLDS = "com|fr|net|org|io|be|info|biz|lu|ch|me|ly|co|ee|gg|shop|store|app|xyz"
_LINK_RE = re.compile(
    r"https?://\S{1,2000}|www\.\S{1,2000}"
    rf"|(?<![a-z0-9.-])(?:[a-z0-9-]{{1,63}}\.){{1,8}}(?:{_TLDS})/\S{{1,2000}}"
    rf"|(?<![a-z0-9.-])(?:[a-z0-9-]{{1,63}}\.){{1,8}}(?:{_BARE_TLDS})\b"
)
_QUEUED_LINK_RE = re.compile(r"(?<![a-z0-9.-])(?:[a-z0-9-]{1,63}\.){1,8}(?:de|eu)(?![a-z0-9./-])")
_TRAILING = ".,;:!?)]»\"'"
# « état.Me contacter » is two sentences; « MonSite.fr », « T.me/jean » are sites.
_SENTENCE_TLDS = ("me", "info", "de", "eu")
_IBAN_RE = re.compile(
    r"(?<![a-z0-9])[a-z]{2}(?:\d{2}[a-z0-9]{11,30}"
    r"|[\s.\-/_]?\d{2}(?:[\s.\-/_][a-z0-9]{1,11}){2,8})(?![a-z0-9])"
)


def _words(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])")


_PAYING_RE = re.compile(
    r"(?<![a-z])(?:pai(?:e|ement)\w*|pay(?:er|ez)|regl\w*|rembours\w*|virement\w*"
    r"|transfert\w*|accept\w*)(?![a-z])"
)


_MESSAGING_RE = re.compile(r"(?<![a-z])(?:" + "|".join(MESSAGING) + ")")
_PAYMENT_APPS_RE = _words(PAYMENT_APPS)
_PAYMENT_WORDS_RE = _words(PAYMENT_WORDS)
_NETWORKS_RE = re.compile(
    r"(?<![a-z])(?<!polaroid )(?:" + "|".join(SOCIAL_NETWORKS) + r")(?![a-z])"
)
# A mail provider named, with the word before it (the name of the address).
# A mail provider after a word that reads as an address (« jean.dupont gmail », « jean75
# hotmail »): masked. Named alone (« écris-moi sur gmail », « Mug Gmail »): queued.
_PROVIDERS_RE = re.compile(
    r"(?<![a-z0-9._%+-])(?=[a-z0-9._%+-]{0,63}[0-9._])[a-z0-9._%+-]{1,64}+"
    r"(?:\s*,\s*|\s+(?:sur\s+)?)(?:" + "|".join(MAIL_PROVIDERS) + r")(?![a-z])"
)
_PROVIDER_NAMED_RE = _words(PROVIDERS_NAMED_ALONE)
_MAIL_WORD_RE = re.compile(r"(?<![a-z])(?:e-?mail|mail|adresse|ecri[rsv]\w*)(?![a-z])")


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


def _series(values: Sequence[str]) -> bool:
    """Three numbers or more by a small constant step: sizes, postcodes, issues (« 36 38 40
    42 », « 30 40 50 »), never « 01 23 45 67 89 »."""
    if len(values) < 3 or any(len(v) > 6 for v in values):
        return False  # « 1111…1 » of 5000 digits: no size, and no int to read
    numbers = [int(v) for v in values]
    steps = {b - a for a, b in pairwise(numbers)}
    return len(numbers) >= 3 and len(steps) == 1 and 0 < abs(next(iter(steps))) <= 10


def _hours(passage: str) -> bool:
    """Only times of the day: « 08:30-12:00 / 14:00-18:30 »."""
    return bool(_TIME_RE.search(passage)) and not re.search(r"\d", _TIME_RE.sub("", passage))


def _iban_confidence(passage: str) -> float:
    compact = re.sub(r"[\s.\-/_]", "", passage)
    bban = compact[4:]
    if sum(c.isdigit() for c in bban) < 10 or sum(c.isalpha() for c in bban) > 6:
        return 0
    if iban_valid(compact):
        return 0.99
    return 0.9 if IBAN_LENGTHS.get(compact[:2]) == len(compact) else 0


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
        """Each phone number of a run of digits (« 06 12 34 56 78 - 2 kg » has one, followed by
        a weight), then what is left of the run, item by item (« 2015, 125 000 km »)."""
        found: list[Detection] = []
        text = self.norm.text
        for run in _RUN_RE.finditer(text):
            groups = [
                (run.start() + g.start(), run.start() + g.end())
                for g in _GROUP_RE.finditer(run.group())
            ]
            rest = run.start()
            i = len(groups) if _hours(run.group()) else 0  # « 08:30-12:00 / 14:00 »
            while i < len(groups):
                end = self._phone(run, groups, i)
                if end is None:
                    i += 1
                    continue
                start = run.start() if i == 0 else groups[i][0]
                found += self._items(rest, start)
                found.append(self.at("phone", start, groups[end - 1][1], 0.95))
                rest, i = groups[end - 1][1], end
            found += self._items(rest, run.end())
        return found

    def _phone(self, run: re.Match[str], groups: list[tuple[int, int]], i: int) -> int | None:
        """The end (exclusive) of the groups from the `i`-th that make a phone number, if any."""
        text = self.norm.text
        start = run.start() if i == 0 else groups[i][0]
        if i == 0 and (run.group().startswith("+") or run.group().startswith("00")):
            digits = re.sub(r"\D", "", run.group())
            before = text[max(0, start - 32) : start]
            if 9 <= len(digits) <= 15 and not _FR_PHONE_RE.match(digits):
                return (
                    None if _REFERENCE_RE.search(before) else len(groups)
                )  # « +32 470 12 34 56 »: abroad, the whole run
        digits = ""
        for j in range(i, len(groups)):
            digits += text[groups[j][0] : groups[j][1]]
            if len(digits) > 13:
                return None
            if _FR_PHONE_RE.fullmatch(digits) and self._phone_shape(start, groups[i : j + 1], run):
                return j + 1
        return None

    def _phone_shape(self, start: int, groups: list[tuple[int, int]], run: re.Match[str]) -> bool:
        """Not a list (« 06, 2019, 1 000 », but a mobile number « 061, 234, 5678 »), a series
        (« 07 08 09 10 »), a month and its mileage (« 06 2023 8 900 km »), nor a fixed-line
        number after « réf. » (a mobile number is always one: « réf. » before it is a trick)."""
        text = self.norm.text
        passage = text[start : groups[-1][1]]
        values = [text[a:b] for a, b in groups]
        digits = "".join(values)
        mobile = bool(_MOBILE_RE.fullmatch(digits))
        years = any(_LONE_YEAR_RE.fullmatch(v) for v in values[1:])
        unit = bool(_UNIT_RE.search(text[run.end() : run.end() + 12]))
        listed = _LIST_ITEM_SEP_RE.search(passage) and any(len(v) > 2 for v in values)
        if listed and (years or unit or not mobile):
            return False
        if _series(values) or (years and unit):
            return False
        before = text[max(0, start - 32) : start]
        return mobile or not _REFERENCE_RE.search(before)

    def _items(self, start: int, end: int) -> list[Detection]:
        found: list[Detection] = []
        for item in _ITEM_RE.finditer(self.norm.text, start, end):
            confidence = self._run_confidence(item.group(), item.start(), item.end())
            if confidence:
                found.append(self.at("obfuscated_number", item.start(), item.end(), confidence))
        return found

    def _run_confidence(self, run: str, start: int, end: int) -> float:
        """Q31: nine digits or more masked, eight queued; a reference, a barcode, a measure, a
        price, a series of sizes or fractions queued; hours, years let go, and the digits
        around a year (« PS5 2020 1 500 ») counted apart."""
        if _hours(run):
            return 0
        longest = max(len(re.sub(r"\D", "", piece)) for piece in _LONE_YEAR_RE.split(run))
        if longest < 8:
            return 0
        digits = re.sub(r"\D", "", run)
        before = self.norm.text[max(0, start - 32) : start]
        after = self.norm.text[end : end + 8]
        written = self.text[slice(*self.norm.span(start, end))]  # « 1 2 3 4 » as written
        doubtful = (
            _REFERENCE_RE.search(before)
            or _NUMBER_SIGN_RE.search(before)
            or _UNIT_RE.search(after)
            or ean_valid(digits)
            or isbn10_valid(digits)
            or _series(_GROUP_RE.findall(written))
            or _FRACTIONS_RE.fullmatch(run)
        )
        return 0.5 if doubtful or longest < 9 else 0.9

    def ibans(self) -> list[Detection]:
        """An IBAN of a known country: sure with its check digits, a typo at its exact length;
        else two letters and digits (« GT 86 2015 », « MT-07 2019 ») are no IBAN."""
        found: list[Detection] = []
        for m in _IBAN_RE.finditer(self.norm.text):
            # The word after an IBAN may be read as its last group (« … 606 merci »): the
            # groups are dropped from the right until the IBAN holds.
            ends = [m.start() + g.end() for g in re.finditer(r"[a-z0-9]+", m.group())]
            for end in reversed(ends[1:]):
                confidence = _iban_confidence(self.norm.text[m.start() : end])
                if confidence:
                    found.append(self.at("iban", m.start(), end, confidence))
                    break
        return found

    def addresses(self) -> list[Detection]:
        """E-mail addresses, with or without their domain; « insta @jean » is a handle."""
        found: list[Detection] = []
        for pattern, confidence in (
            (_EMAIL_RE, 0.95),
            (_ADDRESS_RE, 0.9),
            (_SPACED_ADDRESS_RE, 0.9),
        ):
            for m in pattern.finditer(self.norm.text):
                name = m.group().partition("@")[0]
                if name != name.rstrip() and name.strip() in SOCIAL_NETWORKS:
                    continue
                found.append(self.at("email", m.start(), m.end(), confidence))
        return found

    def providers(self) -> list[Detection]:
        """A provider named alone: masked after « écris-moi », « mon adresse »…, else queued
        (« Mug Gmail »)."""
        found: list[Detection] = []
        for m in _PROVIDER_NAMED_RE.finditer(self.norm.text):
            asked = _MAIL_WORD_RE.search(self.norm.text[max(0, m.start() - 30) : m.start()])
            found.append(self.at("email", m.start(), m.end(), 0.9 if asked else 0.6))
        return found

    def links(self) -> list[Detection]:
        found: list[Detection] = []
        for m in _LINK_RE.finditer(self.norm.text):
            link = m.group().rstrip(_TRAILING)  # « www.site.fr. »: the sentence's dot
            if not link:
                continue
            detection = self.at("external_link", m.start(), m.start() + len(link), 0.9)
            tld = detection.excerpt.rsplit(".", 1)[-1]
            bare = not link.startswith(("http", "www."))
            if bare and "/" not in link and tld[:1].isupper() and tld.lower() in _SENTENCE_TLDS:
                continue  # « état.Me contacter » is two sentences, not a site
            host = re.sub(r"^(?:https?://)?(?:www\.)?", "", link).split("/")[0]
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
            *f.addresses(),
            *f.all(_PROVIDERS_RE, "email", 0.9),
            *f.providers(),
            *f.all(_AT_SIGN_RE, "email", 0.5),
            *f.all(_HANDLE_RE, "social_handle", 0.9),
            *f.links(),
            *f.all(_QUEUED_LINK_RE, "external_link", 0.6),
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
