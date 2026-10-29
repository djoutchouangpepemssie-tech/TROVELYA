"""Ordinary listings (vehicles, phones, opening hours, sizes) and the tricks of the third review
of P2-T05a1: a phone number glued to a measure or after a reference is still masked; dates,
years, models, providers, sentence ends, fractions and lists of sizes are never masked."""

import re

import pytest

from trovelya.modules.circumvention.rules import MASK, MASK_AT, detect, mask


def _shown(text: str) -> str:
    return mask(text, detect(text))


@pytest.mark.parametrize(
    "text",
    [
        "06 12 34 56 78 - 2 kg",
        "0612345678 1 l",
        "Retrait à Lyon 06 12 34 56 78 5 km de Lyon",
        "Réf 2 06 12 34 56 78",
        "isbn 2070612759 06 12 34 56 78",
        "mon tel 01 23 45 67 89",  # 0123456789 is a valid ISBN-10: a fixed line all the same
        "Tél n° 01 23 45 67 89",
    ],
)
def test_phone_inside_a_longer_run_masked(text: str) -> None:
    assert any(d.signal == "phone" and d.confidence >= MASK_AT for d in detect(text)), detect(text)
    shown = _shown(text)
    assert not re.search(r"\d\d\W{0,4}\d\d\W{0,4}\d\d", shown.replace("2070612759", "")), shown


@pytest.mark.parametrize("text", ["Appelle 6 12 34 56 78 l'après-midi", "6 12 34 56 78 m'écrire"])
def test_letter_with_an_apostrophe_is_no_unit(text: str) -> None:
    assert MASK in _shown(text), detect(text)


def test_two_phones_two_detections() -> None:
    found = [d for d in detect("0612345678 0712345678") if d.signal == "phone"]
    assert len(found) == 2, found


@pytest.mark.parametrize(
    "text",
    [
        # Dates, years, models and kilometres (finding 2)
        "1ère main, MEC 07/2016, 9 800 km",
        "Achetée en 06/2021 1 200 €",
        "Facture 07/2023, 2 499 €",
        "Garantie jusqu'en 07/2027, 1 200 € ferme",
        "Yamaha MT-07 2019 8 500 km",
        "Révision faite à 06 2023 8 900 km",
        "Tome 06, 2019, 1 000 exemplaires",
        "Tailles 06, 08, 10, 12, 14 ans",
        "Numéros 07 08 09 10 11 de la revue",
        # Two letters and digits are no IBAN (finding 3)
        "Toyota GT 86 2015 75 000 km 200 ch",
        "Moto Yamaha MT-07 2019 12 300 km 689 cm3",
        "Renault Zoé ZE 40 2019 35 000 km 41 kWh",
        "Kawasaki ZX 10 2018 20 000 km 1 000 cc",
        "TV 55 2022 4K 120 Hz 899 €",
        "Vends le 12 03 2024 1 500 km",
        "Ma 12 13 14 15 16 17 18",
        "cm 30 40 50 60 70 80 90 100",
        "Dispo en 38 1/2 39 1/2 40 1/2",
        # Operators, software, the post (finding 4)
        "iPhone 12 acheté chez Orange, débloqué tout opérateur.",
        "Box internet de chez Free",
        "Samsung A52 acheté chez SFR en 2022.",
        "Envoi par laposte uniquement",
        "iPhone 11 sans compte iCloud, débloqué.",
        "Verrouillage iCloud retiré",
        "Pack Office 2019 : Word, Excel, PowerPoint, Outlook.",
        "Licence Microsoft Outlook 2021",
        "Mug Gmail logo",
        # Sentence ends and slashes (finding 5)
        "très bon état. de plus il est livré avec sa housse",
        "vendu avec facture. info : retrait uniquement",
        "pas de rayure. eu peu servi",
        "livré complet . de couleur noire",
        "neuf jamais servi.de couleur bleue",
        "Coloris bleu.vert/rouge",
        "Tissu coton.lin/soie",
        "Pneus été.hiver/4 saisons",
        "annonce.vélo/trottinette",
        # Hours, screens, fractions, surfaces, years and prices (finding 6)
        "Horaires 08:30-12:00 / 14:00-18:30",
        "Ouvert 9:00-12:00 14:00-19:00",
        "Écran 1920\u00d71080 2560\u00d71440",
        "Pointures 38 ½ 39 ½ 40 ½",
        "Tuyau 3/4 1/2 1/4 3/8 5/8",
        "Appartement 65 m² 1 215 000 € 3 chambres",
        "PS5 2020 1 500 €",
        "iPhone13 2021 1 099 €",
        # A lone « @ » between words (finding 7)
        "Rendez-vous @ Lyon Part-Dieu",
        "Livraison possible @ domicile",
        "Collection Automne @ Hiver 2024",
        "Vendu par Jean @ la boutique",
        # Lists of sizes, postcodes, series (finding 8) and invoice numbers (finding 10)
        "Lot de 8 tee-shirts tailles 36 38 40 42 44 46 48 50",
        "Pointures 39 40 41 42 43 44 45",
        "Taille 34/36/38/40/42",
        "Codes postaux couverts : 75001 75002 75003 75004",
        "Playmobil 70000 70001 70002 70003",
        "Saison 1 2 3 4 5 6 7 8 9",
        "N° 123456789",
        "Facture d'achat 2023 n° 123456789",
        "Commande du 03/04/2025, n° 112-3456789-1234567",
    ],
)
def test_ordinary_listing_never_masked(text: str) -> None:
    assert _shown(text) == text, detect(text)


def test_iban_needs_a_country_and_its_length() -> None:
    assert {d.signal for d in detect("BE68 5390 0754 7034")} == {"iban"}
    assert all(d.signal != "iban" for d in detect("ZZ76 3000 6000 0112 3456 7890 189"))


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("Va sur www.site.fr.", "."),
        ("voir www.site.fr/page).", ")."),
    ],
)
def test_link_mask_keeps_the_punctuation(text: str, kept: str) -> None:
    assert _shown(text).endswith(MASK + kept), _shown(text)


@pytest.mark.parametrize("text", ["T.me/jeandupont", "MonSite.fr", "Wa.Me/jean"])
def test_capital_letters_hide_no_link(text: str) -> None:
    assert _shown(text) == MASK, detect(text)


@pytest.mark.parametrize("text", ["Insta @jean.dupont", "TikTok @jean"])
def test_handle_after_a_network_is_a_handle(text: str) -> None:
    signals = {d.signal for d in detect(text) if d.confidence >= MASK_AT}
    assert signals == {"social_handle"}, detect(text)


@pytest.mark.parametrize(
    "text",
    ["jean@gmail", "jean @ gmail", "jean.dupont outlook", "jean75 hotmail"],
)
def test_address_without_its_domain_masked(text: str) -> None:
    assert MASK in _shown(text), detect(text)


@pytest.mark.parametrize(
    "text",
    [
        # Any separator between the groups (fourth review, B1)
        "06!12!34!56!78",
        "06=12=34=56=78",
        "06\u20ac12\u20ac34\u20ac56\u20ac78",
        "06\u00d712\u00d734\u00d756\u00d778",
        "06\U0001f64212\U0001f64234\U0001f64256\U0001f64278",
        "06{12}34{56}78",
        "Score 06 - 12 = 34 > 56 > 78",
        "06 12 34 56=78",
        "06 12 34 \u20ac 56 78",
        "06.12.34.56%78",
        "06\u00d712 34 56 78",
        "01 45 67 89=10",
        "1 200 \u20ac 06 12 34 56 78",
        # A mobile number written as a list (B2)
        "061, 234, 5678",
        "0612; 3456; 78",
        # « n° » before a fixed line (C1), an operator's address (C2, C4)
        "mon n° 01 45 67 89 10",
        "contact no 01 45 67 89 10",
        "jean @ gmx",
        "jean @ aol",
        "jean.dupont chez orange.fr",
        "jean.dupont sur gmail",
        # A month written before the rest of the number (C6)
        "06/2012 34 56 78",
    ],
)
def test_phone_and_address_tricks_masked(text: str) -> None:
    shown = _shown(text)
    assert MASK in shown, detect(text)
    assert not re.search(r"\d\d\W{0,4}\d\d\W{0,4}\d\d", shown), shown
    for part in ("jean", "gmx", "aol", "orange", "gmail"):
        assert part not in shown.lower(), shown


@pytest.mark.parametrize(
    "text",
    [
        "FR14 2004 1010 0505 0001 3M02 606 merci",
        "FR76 3000 6000 0112 3456 7890 189 pour le paiement",
    ],
)
def test_iban_followed_by_a_word_masked(text: str) -> None:
    assert {d.signal for d in detect(text) if d.confidence >= MASK_AT} == {"iban"}, detect(text)
    assert _shown(text).startswith(MASK + " "), _shown(text)


@pytest.mark.parametrize("text", ["Tracteur 03 2018 1 200 heures", "MEC 04 2019 1 500 kilomètres"])
def test_month_year_and_hours_never_masked(text: str) -> None:
    assert _shown(text) == text, detect(text)


@pytest.mark.parametrize("text", ["1" * 4301, "prix " + "9" * 5000], ids=["4301", "5000"])
def test_very_long_number_does_not_crash(text: str) -> None:
    assert MASK in _shown(text)


def test_bare_de_or_eu_site_queued() -> None:
    found = detect("visitez monsite.eu")
    assert [(d.signal, d.confidence) for d in found] == [("external_link", 0.6)], found


@pytest.mark.parametrize(
    "text",
    [
        "FR1420041010050500013M02606",
        "FR7630006000011234567890189",
        "BE68539007547034",
        "GB29NWBK60161331926819",
        "NL91ABNA0417164300",
    ],
)
def test_iban_without_spaces_masked_whole(text: str) -> None:
    assert _shown(text) == MASK, detect(text)
    assert max(d.confidence for d in detect(text) if d.signal == "iban") == 0.99


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("06/2019 06 12 34 56 78", MASK),  # a month before a mobile number
        ("Taille 06 = 36 €, 08 = 38 €, 10 = 40 €", None),  # prices, not a number
        ("Note: 1,5 sur gmail", None),
        ("adresse : outlook", MASK),
    ],
)
def test_fourth_review_cases(text: str, shown: str | None) -> None:
    assert MASK not in _shown(text) if shown is None else _shown(text).endswith(shown)
    if shown == MASK:  # the date may stay, never a digit of the number
        assert not re.search(r"\d\d", _shown(text).replace("06/2019", "").replace(MASK, ""))
