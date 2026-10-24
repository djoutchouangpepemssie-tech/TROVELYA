"""Member preferences `GET/PUT /v1/me/preferences` (P1-T06c, section 7.3, E11)."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import client, make_account

__all__ = ["client"]

VALID: dict[str, Any] = {
    "interests": ["mode", "montres_bijoux", "collection"],
    "sizes": {"top": "M", "shoe_eu": "42"},
    "budget_max_minor": 150_00,
    "blocked_brands": ["MarqueX"],
    "feed_discovery_level": 70,
    "paused_categories": ["vehicules"],
    "not_now_until": "2026-11-01T00:00:00Z",
    "personalised_feed": False,
    "notification_settings": {
        "email": {"new_message": True, "price_drop": False},
        "push": {"new_message": True},
    },
}


async def test_defaults_then_replace(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    member = await make_account(sessionmaker, completed=True)
    defaults = (await client.get("/v1/me/preferences", headers=member.headers)).json()
    assert defaults == {
        "interests": [],
        "sizes": {},
        "budget_max_minor": None,
        "blocked_brands": [],
        "feed_discovery_level": 50,
        "paused_categories": [],
        "not_now_until": None,
        "personalised_feed": True,
        "notification_settings": {},
    }
    saved = await client.put("/v1/me/preferences", headers=member.headers, json=VALID)
    assert saved.status_code == 200, saved.text
    again = (await client.get("/v1/me/preferences", headers=member.headers)).json()
    assert again == saved.json()
    assert again["interests"] == VALID["interests"] and again["sizes"] == VALID["sizes"]
    assert again["notification_settings"] == VALID["notification_settings"]
    # PUT replaces everything: what is not sent goes back to its default.
    reset = await client.put("/v1/me/preferences", headers=member.headers, json={})
    assert reset.json() == defaults


@pytest.mark.parametrize(
    "change",
    [
        {"interests": ["mode", "pas_un_univers"]},
        {"interests": ["mode", "mode"]},
        {"paused_categories": ["inconnu"]},
    ],
)
async def test_preferences_unknown_universe_422(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, change: dict[str, Any]
) -> None:
    member = await make_account(sessionmaker, completed=True)
    response = await client.put(
        "/v1/me/preferences", headers=member.headers, json={**VALID, **change}
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("sizes", "status"),
    [
        ({f"size_{chr(97 + i)}": "M" for i in range(10)}, 200),
        ({f"size_{chr(97 + i)}": "M" for i in range(11)}, 422),
        ({"Top": "M"}, 422),
        ({"t": "M"}, 422),
        ({"top": "x" * 11}, 422),
        ({"top": ""}, 422),
        ({"top": 42}, 422),
    ],
)
async def test_preferences_sizes_bounds(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    sizes: dict[str, Any],
    status: int,
) -> None:
    member = await make_account(sessionmaker, completed=True)
    response = await client.put(
        "/v1/me/preferences", headers=member.headers, json={**VALID, "sizes": sizes}
    )
    assert response.status_code == status


@pytest.mark.parametrize(
    "change",
    [
        {"notification_settings": {"sms": {"new_message": True}}},
        {"notification_settings": {"email": {"new_message": "oui"}}},
        {"notification_settings": {"email": {"Bad-Type": True}}},
        {"feed_discovery_level": 101},
        {"feed_discovery_level": -1},
        {"budget_max_minor": -1},
        {"blocked_brands": ["x" * 81]},
        {"blocked_brands": [f"m{i}" for i in range(101)]},
        {"unknown_field": True},
    ],
)
async def test_preferences_other_bounds_422(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, change: dict[str, Any]
) -> None:
    member = await make_account(sessionmaker, completed=True)
    response = await client.put(
        "/v1/me/preferences", headers=member.headers, json={**VALID, **change}
    )
    assert response.status_code == 422


async def test_preferences_need_a_completed_profile(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    incomplete = await make_account(sessionmaker)
    assert (await client.get("/v1/me/preferences", headers=incomplete.headers)).status_code == 403
