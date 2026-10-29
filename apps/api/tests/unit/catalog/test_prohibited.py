"""Prohibited items in a listing's text (section 8.17, plan Q33, Q34): a term without ambiguity
is refused with its reason, an ambiguous one goes to review, known innocent phrases are never
flagged. Accents, capitals, look-alike digits (« r0lex ») and punctuation make no difference."""

import pytest

from trovelya.modules.catalog.service.moderation import PROHIBITED, prohibited

REFUSED = [
    ("Fusil de chasse calibre 12", "weapons"),
    ("Lot de munitions 9 mm", "weapons"),
    ("Montre R0LEX contrefaçon parfaite", "counterfeit"),
    ("Sac faux Louis Vuitton", "counterfeit"),
    ("Boîte de Xanax", "medicines"),
    ("Médicaments périmés", "medicines"),
    ("Cocaïne", "drugs"),
    ("Paquet de cigarettes neuf", "tobacco"),
    ("E-liquide fraise 10 ml", "tobacco"),
    ("Bouteille de whisky 12 ans", "alcohol"),  # Q33: alcohol refused for everyone in P2
    ("Lot de 6 bouteilles de vin", "alcohol"),
    ("Chiots labrador à vendre", "animals"),
    ("Défense d'éléphant sculptée", "protected_species"),
    ("Sextoy neuf jamais servi", "adult"),
    ("Compte Netflix premium", "digital_accounts"),
    ("Billet de train Paris Lyon", "transport_tickets"),
    ("Produit rappelé par le fabricant", "recalled"),
    ("Vélo volé, prix cassé", "stolen"),
    ("Passeport français", "identity_documents"),
]


@pytest.mark.parametrize(("text", "reason"), REFUSED)
def test_prohibited_refused_with_reason(text: str, reason: str) -> None:
    found = prohibited(text, "")
    assert (found.outcome, found.reasons) == ("refused", (reason,)), found


REVIEWED = [
    ("Pistolet ancien de collection", "weapons"),
    ("Réplique airsoft", "weapons"),
    ("Robe couleur champagne et vin", "alcohol"),
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
