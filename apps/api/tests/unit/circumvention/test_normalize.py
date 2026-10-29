"""Normalisation before detection (section 8.16): what the text becomes, and that every
character still points to the passage of the original it comes from."""

import pytest

from trovelya.modules.circumvention.normalize import normalize


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("ÉCRIVEZ", "ecrivez"),
        ("zéro six douze", "0 6 12"),
        ("soixante-dix-huit", "78"),
        ("quatre-vingt-dix-neuf", "99"),
        ("zérosix", "06"),
        ("zéro6 12", "06 12"),
        ("06​12­34⁠56", "06123456"),  # invisible characters dropped
        ("0️⃣6️⃣", "06"),  # keycap emojis
        ("\uff10\uff16\uff11\uff12", "0612"),  # full width
        ("٠٦١٢", "0612"),  # Arabic-Indic digits
        ("O6 l2", "06 12"),  # letters among digits
        ("wh\u0430tsapp", "whatsapp"),  # Cyrillic a
        ("jean [at] gmail point com", "jean@gmail.com"),
        ("jean (a) gmail (.) com", "jean@gmail.com"),
        ("jean arobase gmail", "jean@gmail"),
        ("jean at gmail dot com", "jean@gmail.com"),
        ("jean point dupont arobase web point de", "jean.dupont@web.de"),
        ("Facture du 03/05/2022 18 mois", "facture du § 18 mois"),
    ],
)
def test_normalized(text: str, normalized: str) -> None:
    assert normalize(text).text == normalized


@pytest.mark.parametrize(
    "text",
    ["septembre", "une douzaine", "sixième", "point relais", "Signal d'usure", "dixit"],
)
def test_words_left_alone(text: str) -> None:
    """A number word inside a longer word, or « point » that is no dot, stays as it is (a
    word on its own, « neuf », becomes a digit: harmless out of a run of eight)."""
    assert not any(c.isdigit() for c in normalize(text).text)


def test_every_character_points_into_the_original() -> None:
    text = "Écrivez : zéro six, douze​ trente-quatre ! ﬁn"
    norm = normalize(text)
    assert len(norm.origin) == len(norm.text)
    for start, end in norm.origin:
        assert 0 <= start < end <= len(text)
