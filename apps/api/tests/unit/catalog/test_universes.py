"""One list of universe keys for the whole application (P2 plan, review point 2)."""

import pytest
from pydantic import ValidationError

from trovelya.modules.catalog import universes as catalog_universes
from trovelya.modules.identity import universes as identity_universes
from trovelya.modules.identity.schemas import Preferences


def test_universe_keys_single_source() -> None:
    assert identity_universes.UNIVERSE_KEYS is catalog_universes.UNIVERSE_KEYS


def test_sixteen_stable_keys() -> None:
    # The keys saved as interests since P1 (E11 of the P1 plan) never change.
    assert catalog_universes.UNIVERSE_KEYS == (
        "mode",
        "montres_bijoux",
        "maison_jardin",
        "high_tech",
        "culture_loisirs",
        "collection",
        "enfants_bebe",
        "sport_plein_air",
        "art_antiquites",
        "beaute_bien_etre",
        "animaux",
        "materiel_pro",
        "vehicules",
        "immobilier",
        "services",
        "autres",
    )


def test_preferences_still_accept_universe_keys() -> None:
    Preferences.model_validate({"interests": ["mode", "autres"], "paused_categories": ["animaux"]})
    with pytest.raises(ValidationError):
        Preferences.model_validate({"interests": ["voitures"]})
