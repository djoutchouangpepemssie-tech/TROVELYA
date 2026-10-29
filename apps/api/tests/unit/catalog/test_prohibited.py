"""Prohibited items in a listing's text (section 8.17, plan Q33, Q34): a term without ambiguity
is refused with its reason, an ambiguous one goes to review, known innocent phrases are never
flagged. Accents, capitals, look-alike digits (« r0lex ») and punctuation make no difference."""

from pathlib import Path

import pytest

from trovelya.modules.catalog.service.moderation import PROHIBITED, prohibited

REFUSED = [
    ("Fusil de chasse calibre 12", "weapons"),
    ("Lot de munitions 9 mm", "weapons"),
    ("Montre R0LEX contrefaçon parfaite", "counterfeit"),
    ("Sac faux Louis Vuitton", "counterfeit"),
    ("Boîte de Xanax", "medicines"),
    ("Lot de médicaments périmés", "medicines"),
    ("Cannabis", "drugs"),
    ("Paquet de cigarettes neuf", "tobacco"),
    ("E-liquide fraise 10 ml", "tobacco"),
    ("Bouteille de whisky 12 ans", "alcohol"),  # Q33: alcohol refused for everyone in P2
    ("Lot de 6 bouteilles de vin", "alcohol"),
    ("Chiots labrador à vendre", "animals"),
    ("Défense d'éléphant sculptée", "protected_species"),
    ("Sextoy neuf jamais servi", "adult"),
    ("Compte Netflix premium", "digital_accounts"),
    ("Billets nominatifs pour le concert", "transport_tickets"),
    ("Produit rappelé par le fabricant", "recalled"),
    ("Vélo volé, prix cassé", "stolen"),
    ("Passeport vierge", "identity_documents"),
]


@pytest.mark.parametrize(("text", "reason"), REFUSED)
def test_prohibited_refused_with_reason(text: str, reason: str) -> None:
    found = prohibited(text, "")
    assert (found.outcome, found.reasons) == ("refused", (reason,)), found


REVIEWED = [
    ("Pistolet ancien de collection", "weapons"),
    ("Airsoft M4 complet", "weapons"),
    ("Vin rouge de Bordeaux", "alcohol"),
    ("Statuette en ivoire", "protected_species"),
    ("Héroïne du roman, tome 2", "drugs"),
    ("Billets pour le concert de samedi", "transport_tickets"),
    ("iPhone sans facture", "stolen"),
]


@pytest.mark.parametrize(("text", "reason"), REVIEWED)
def test_ambiguous_term_goes_to_review(text: str, reason: str) -> None:
    found = prohibited(text, "")
    assert (found.outcome, found.reasons) == ("review", (reason,)), found


@pytest.mark.parametrize(
    "text",
    [
        "Pistolet à colle chaude Bosch",
        "Pistolet à peinture",
        "Fusil à aiguiser en acier",
        "Cave à vin 24 bouteilles",
        "Verres à whisky en cristal",
        "Flûtes à champagne",
        "Porte-passeport en cuir",
        "Livre de préparation au permis de conduire",
        "Billets de banque anciens",
        "Peluche lapin",
        "Armoire en chêne",
        "Charmante lampe",
        "Robe en lin bleue, portée deux fois",
        "Volet roulant",
        "L'avion vole bien",
    ],
)
def test_exceptions_not_flagged(text: str) -> None:
    found = prohibited(text, "")
    assert found.outcome == "online", found


def test_description_is_read_too() -> None:
    assert prohibited("Lot de bouteilles", "Whisky et vodka").reasons == ("alcohol",)


def test_refusal_wins_over_review() -> None:
    found = prohibited("Pistolet", "Fusil de chasse et munitions")
    assert (found.outcome, found.reasons) == ("refused", ("weapons",))


def test_every_reason_has_a_readable_label() -> None:
    """Each motive of 8.17 (and the drugs) is a reason code with its French label."""
    assert " ".join(PROHIBITED.reasons) == (
        "weapons counterfeit medicines drugs tobacco alcohol animals protected_species adult"
        " digital_accounts transport_tickets recalled stolen identity_documents"
    )
    assert all(label and label[0].isupper() for label in PROHIBITED.labels.values())


@pytest.mark.parametrize(
    ("text", "reason"),
    [("Peluche chiot", "animals"), ("Fusil de chasse jouet en plastique", "weapons")],
)
def test_a_word_changing_the_object_turns_refusal_into_review(text: str, reason: str) -> None:
    found = prohibited(text, "")
    assert (found.outcome, found.reasons) == ("review", (reason,)), found


def _corpus(name: str) -> list[str]:
    lines = (Path(__file__).parent / "data" / name).read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


@pytest.mark.parametrize("text", _corpus("honest_listings.txt"))
def test_honest_listing_never_refused(text: str) -> None:
    """A refusal is final (`removed`): an honest listing is at worst reviewed."""
    assert prohibited(text, "Très bon état.").outcome != "refused"


@pytest.mark.parametrize("text", _corpus("prohibited_listings.txt"))
def test_prohibited_listing_never_online(text: str) -> None:
    """Misspelt, spaced out, in English or in slang: refused or reviewed, never online."""
    assert prohibited(text, "Très bon état.").outcome != "online"


def test_masked_text_cut_before_a_mask() -> None:
    from trovelya.modules.catalog.service.moderation import _fit  # pyright: ignore[reportPrivateUsage]
    from trovelya.modules.circumvention.service import MASK

    cut = _fit(f"Vélo {MASK} {MASK} {MASK}", 120)
    assert len(cut) <= 120 and cut.endswith("…")
    assert cut.replace(MASK, "").strip(" …") == "Vélo"
