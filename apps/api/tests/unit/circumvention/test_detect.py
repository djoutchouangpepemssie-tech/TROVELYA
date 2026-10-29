"""Contact details hidden in a text (section 8.16, plan P2-T05a, Q12, Q30, Q31): what is found,
how sure, what is masked. Pure functions: no database."""

import re
import time

import pytest

from trovelya.modules.circumvention.rules import MASK, MASK_AT, detect, iban_valid, mask


def _found(text: str) -> dict[str, float]:
    """The surest confidence of each signal found."""
    found: dict[str, float] = {}
    for d in detect(text):
        found[d.signal] = max(found.get(d.signal, 0.0), d.confidence)
    return found


MASKED = [
    ("Appelez le 06 12 34 56 78 le soir", "phone"),
    ("joignable au 06.12.34.56.78", "phone"),
    ("0 6 1 2 3 4 5 6 7 8", "phone"),
    ("zéro six douze trente-quatre cinquante-six soixante-dix-huit", "phone"),
    ("zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit", "phone"),
    ("zérosix 12 34 56 78", "phone"),
    ("+33 6 12 34 56 78", "phone"),
    ("+33 (0)6 12 34 56 78", "phone"),
    ("(06) 12 34 56 78", "phone"),
    ("0033 6-12-34-56-78", "phone"),
    ("06_12_34_56_78", "phone"),
    ("06*12*34*56*78", "phone"),
    ("06\u201312\u201334\u201356\u201378", "phone"),
    ("06​12​34​56​78", "phone"),
    ("0️⃣6️⃣1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣", "phone"),
    ("O6 12 34 56 78", "phone"),
    ("06 l2 34 56 78", "phone"),
    ("٠٦١٢٣٤٥٦٧٨", "phone"),
    ("+32 470 12 34 56", "phone"),
    ("+352 621 123 456", "phone"),
    ("6 12 34 56 78", "obfuscated_number"),  # nine digits: masked (Q31)
    ("jean [at] gmail point com", "email"),
    ("jean.dupont@gmail.com", "email"),
    ("jean arobase gmail.com", "email"),
    ("jean arobase gmail", "email"),
    ("jean @ gmail . com", "email"),
    ("jean at gmail dot com", "email"),
    ("écris-moi sur gmail", "email"),
    ("FR76 3000 6000 0112 3456 7890 189", "iban"),
    ("FR76-3000-6000-0112-3456-7890-189", "iban"),
    ("FR 76 3000 6000 0112 3456 7890 189", "iban"),
    ("FR76 3000 6000 0112 3456 7890 188", "iban"),  # wrong key: still an IBAN
    ("Contactez-moi sur WhatsApp", "payment_app"),
    ("whatsappez-moi", "payment_app"),
    ("sur_whatsapp", "payment_app"),
    ("Whats​App", "payment_app"),
    ("wh\u0430tsapp", "payment_app"),
    ("whatapp", "payment_app"),
    ("paiement par lydia possible", "payment_app"),
    ("je préfère payer par PayPal", "payment_app"),
    ("insta : @vendeur", "social_handle"),
    ("voir www.mon-site.fr pour plus de photos", "external_link"),
    ("https://exemple.com/annonce", "external_link"),
    ("https://evil.io/trovelya.com", "external_link"),
    ("www.trovelya.fr.mon-site.com", "external_link"),
    ("Mon numéro : 06 12 34 56 78", "phone"),
    ("Tel n° 06 12 34 56 78", "phone"),
    ("réf 06 12 34 56 78", "phone"),  # « réf. » before a mobile is a trick
    ("06~12~34~56~78", "phone"),
    ("06#12#34#56#78", "phone"),
    ("06\u201012\u201134\u221256\u202278", "phone"),
    ("06 -- 12 -- 34 -- 56 -- 78", "phone"),
    ("FR76 30006 00001 12345678901 89", "iban"),
    ("FR76/3000/6000/0112/3456/7890/189", "iban"),
    ("jean (arobase) gmail (point) com", "email"),
    ("jean[@]gmail[.]com", "email"),
    ("jean chez gmail point com", "email"),
    ("j e a n @ g m a i l . c o m", "email"),
    ("what's app", "payment_app"),
    ("mon whats : vendeur", "payment_app"),
    ("w h a t s a p p", "payment_app"),
    ("TeIegram", "payment_app"),
    ("t.me/vendeur", "external_link"),
    ("wa.me/33612345678", "external_link"),
    ("paypal.me/jean", "external_link"),
]


@pytest.mark.parametrize(("text", "signal"), MASKED)
def test_contact_details_masked(text: str, signal: str) -> None:
    found = _found(text)
    assert found.get(signal, 0) >= MASK_AT, detect(text)
    shown = mask(text, detect(text)).replace(MASK, " ")
    # Nothing of the detail left to read: no three digits in a row, no address.
    assert not re.search(r"\d\W{0,4}\d\W{0,4}\d", shown), shown
    for part in ("@", "jean", "gmail", "http", "www"):
        assert part not in shown.lower(), shown


def test_mask_threshold_of_q30() -> None:
    assert MASK_AT == 0.9


QUEUED = [
    ("tailles disponibles 36 38 40 42", "obfuscated_number"),  # eight digits (Q30)
    ("ISBN 0-306-40615-2 en très bon état", "obfuscated_number"),
    ("SN: 0123456789", "obfuscated_number"),
    ("Numéro de série 0123-4567-89", "obfuscated_number"),
    ("Réf 01 02 03 04 05", "obfuscated_number"),
    ("paiement en espèces uniquement", "payment_app"),
    ("Robe de la créatrice Lydia", "payment_app"),  # a first name, no payment around
    ("retrouvez-moi sur insta", "social_handle"),
    ("Vendu à l'unité @15€ la pièce", "email"),  # a lone « @ » of the base rule of 8.16
    ("Réf. produit : 4006381333931", "obfuscated_number"),  # a reference with a word between
    ("Livre 9782070368228", "obfuscated_number"),  # an ISBN-13 by its check digit
    ("Vin Bordeaux 2015 2016 2018 75 cl", "obfuscated_number"),  # a measure
    ("Un compte PayPal", "payment_app"),
    ("Paire de bottes Lydia", "payment_app"),
    ("Robe Lydia 25 €", "payment_app"),
    ("snap : vendeur92", "social_handle"),
]


@pytest.mark.parametrize(("text", "signal"), QUEUED)
def test_doubtful_queued_not_masked(text: str, signal: str) -> None:
    found = _found(text)
    assert 0 < found.get(signal, 0) < MASK_AT, detect(text)
    assert mask(text, detect(text)) == text


@pytest.mark.parametrize(
    "text",
    [
        "Lot de 12 livres",
        "iPhone 13 128 Go",
        "taille 38",
        "année 1857",
        "dimensions 120 x 80 x 75",
        "Robe en lin, portée deux fois, un petit accroc",
        "Vendu 25 €, envoi possible en point relais",
        "Signal d'usure léger sur la semelle",
        "Rangement : 3 tiroirs, 2 portes",
        "Facture du 03/05/2022, 18 mois de garantie restants",
        "Très bon état.Me contacter via la messagerie",
        "Appareil photo Polaroid Snap",
        "Une douzaine de verres, septembre 2021",
        "Voiture 2015, 125 000 km, 5 portes",
        "Moto 125 cm3, 2019, 12 000 km",
        "Chaussures pointures 37, 38, 39, 40, 41",
        "Quantités : 10, 20, 30, 40, 50",
        "Collection Pokémon 151/165, 25/102, 4/102",
        "Ordinateur Dell XPS 13 9310, i7-1165G7",
        "Vinyles 1965 1972 1978 1981",
        "Ancien télégramme de 1916",
    ],
)
def test_no_false_positive(text: str) -> None:
    assert detect(text) == [], detect(text)


def test_iban_checksum() -> None:
    assert iban_valid("FR7630006000011234567890189")
    assert not iban_valid("FR7630006000011234567890188")
    assert (
        _found("FR76 3000 6000 0112 3456 7890 189")["iban"]
        > _found("FR76 3000 6000 0112 3456 7890 188")["iban"]
    )


def test_confidence_decides_the_mask() -> None:
    """At `MASK_AT` exactly, masked; just below, only queued."""
    from trovelya.modules.circumvention.models import Detection

    text = "abc def"
    at = Detection("phone", 0, 3, "abc", MASK_AT)
    below = Detection("phone", 4, 7, "def", MASK_AT - 0.001)
    assert mask(text, [at, below]) == f"{MASK} def"


def test_mask_preserves_rest_of_text() -> None:
    text = "Belle lampe. Appelez le 06 12 34 56 78 ou écrivez à jean@gmail.com. Merci !"
    assert mask(text, detect(text)) == (
        f"Belle lampe. Appelez le {MASK} ou écrivez à {MASK}. Merci !"
    )


def test_whole_obfuscated_address_masked() -> None:
    for text in ("jean (a) gmail.com", "jean point dupont arobase gmail point com"):
        assert mask(text, detect(text)) == MASK, text


def test_spans_point_into_the_original() -> None:
    text = "Écrivez-moi : zéro six douze trente-quatre cinquante-six soixante-dix-huit."
    [found] = detect(text)
    assert text[found.start : found.end] == (
        "zéro six douze trente-quatre cinquante-six soixante-dix-huit"
    )
    assert found.excerpt == text[found.start : found.end]


def test_combining_mark_after_a_passage_masked_with_it() -> None:
    text = "06 12 34 56 78́ merci"
    assert mask(text, detect(text)) == f"{MASK} merci"


@pytest.mark.parametrize(
    "text",
    [
        "a-" * 2500,
        "-a" * 2500,
        "a." * 2500,
        "a" * 5000,
        "1 " * 2500,
        " " * 10000,
        "\n" * 10000,
        "fb " * 3333,
        "@ab " * 2500,
        "rib " * 2500,
        "\ufdfa" * 10000,
    ],
)
def test_long_hostile_text_stays_fast(text: str) -> None:
    """A description of 5000 characters is analysed in a few milliseconds, never in seconds."""
    start = time.perf_counter()
    detect(text)
    assert time.perf_counter() - start < 0.2
