"""Contact details hidden in a text (section 8.16, plan P2-T05a, Q12): what is found, what is
not, and how it is masked. Pure functions: no database."""

import pytest

from trovelya.modules.circumvention.rules import MASK, detect, iban_valid, mask


def _signals(text: str) -> set[str]:
    return {d.signal for d in detect(text)}


@pytest.mark.parametrize(
    ("text", "signal"),
    [
        ("Appelez le 06 12 34 56 78 le soir", "phone"),
        ("joignable au 06.12.34.56.78", "phone"),
        ("0 6 1 2 3 4 5 6 7 8", "phone"),
        ("zéro six douze trente-quatre cinquante-six soixante-dix-huit", "phone"),
        ("+33 6 12 34 56 78", "phone"),
        ("0033 6-12-34-56-78", "phone"),
        ("jean [at] gmail point com", "email"),
        ("jean.dupont@gmail.com", "email"),
        ("jean arobase gmail.com", "email"),
        ("FR76 3000 6000 0112 3456 7890 189", "iban"),
        ("Contactez-moi sur WhatsApp", "payment_app"),
        ("paiement par lydia possible", "payment_app"),
        ("PayPal accepté", "payment_app"),
        ("insta : @vendeur", "social_handle"),
        ("voir www.mon-site.fr pour plus de photos", "external_link"),
        ("https://exemple.com/annonce", "external_link"),
    ],
)
def test_detects_obfuscated_contacts(text: str, signal: str) -> None:
    assert signal in _signals(text), detect(text)


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
    ],
)
def test_no_false_positive(text: str) -> None:
    assert detect(text) == [], detect(text)


def test_long_digit_runs_only_queued() -> None:
    """Eight digits or more that are no phone number (sizes in a row, a reference): the base
    rule of 8.16 flags them, with a confidence too low to mask them on its own."""
    [found] = detect("tailles disponibles 36 38 40 42")
    assert found.signal == "obfuscated_number"
    assert found.confidence < 0.9
    assert mask("tailles disponibles 36 38 40 42", [found]) == "tailles disponibles 36 38 40 42"


def test_iban_checksum() -> None:
    assert iban_valid("FR7630006000011234567890189")
    assert not iban_valid("FR7630006000011234567890188")
    assert "iban" not in _signals("FR76 3000 6000 0112 3456 7890 188")


def test_mask_preserves_rest_of_text() -> None:
    text = "Belle lampe. Appelez le 06 12 34 56 78 ou écrivez à jean@gmail.com. Merci !"
    masked = mask(text, detect(text))
    assert masked == f"Belle lampe. Appelez le {MASK} ou écrivez à {MASK}. Merci !"


def test_spans_point_into_the_original() -> None:
    """Accents, words turned into digits and separators: the span is the original passage."""
    text = "Écrivez-moi : zéro six douze trente-quatre cinquante-six soixante-dix-huit."
    [found] = detect(text)
    assert text[found.start : found.end] == (
        "zéro six douze trente-quatre cinquante-six soixante-dix-huit"
    )
    assert found.excerpt == text[found.start : found.end]


def test_overlapping_detections_masked_once() -> None:
    text = "jean.dupont@gmail.com"
    assert mask(text, detect(text)) == MASK
