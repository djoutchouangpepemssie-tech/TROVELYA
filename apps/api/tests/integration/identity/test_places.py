"""Addresses and search zones (P1-T06b): CRUD, ownership, default zone, 5 km radius."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.identity.test_profile import Account, client, make_account

__all__ = ["client"]

ADDRESS = {
    "label": "Maison",
    "full_name": "Arcel D.",
    "line1": "12 rue de Marseille",
    "postal_code": "69007",
    "city": "Lyon",
    "country_code": "FR",
    "phone_e164": "+33612345678",
    "lat": 45.744212,
    "lon": 4.842374,
}
ZONE = {"label": "Maison", "place_name": "Lyon 7e", "lat": 45.745, "lon": 4.842}


async def _member(sessionmaker: async_sessionmaker[AsyncSession]) -> Account:
    return await make_account(sessionmaker, completed=True)


# --- Addresses -----------------------------------------------------------------------------


async def test_address_crud_and_other_user_404(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    owner, intruder = await _member(sessionmaker), await _member(sessionmaker)
    created = await client.post("/v1/me/addresses", headers=owner.headers, json=ADDRESS)
    assert created.status_code == 201, created.text
    address = created.json()
    assert address["is_default_shipping"] is True  # the first one
    assert (address["lat"], address["lon"]) == (ADDRESS["lat"], ADDRESS["lon"])
    path = f"/v1/me/addresses/{address['id']}"

    patched = await client.patch(path, headers=owner.headers, json={"line2": "Bâtiment B"})
    assert patched.status_code == 200 and patched.json()["line2"] == "Bâtiment B"
    listed = (await client.get("/v1/me/addresses", headers=owner.headers)).json()["data"]
    assert [a["id"] for a in listed] == [address["id"]]

    assert (await client.get("/v1/me/addresses", headers=intruder.headers)).json()["data"] == []
    assert (
        await client.patch(path, headers=intruder.headers, json={"city": "X"})
    ).status_code == 404
    assert (await client.delete(path, headers=intruder.headers)).status_code == 404

    assert (await client.delete(path, headers=owner.headers)).status_code == 204
    assert (await client.get("/v1/me/addresses", headers=owner.headers)).json()["data"] == []
    assert (await client.delete(path, headers=owner.headers)).status_code == 404


async def test_single_default_shipping_address(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    member = await _member(sessionmaker)
    first = (await client.post("/v1/me/addresses", headers=member.headers, json=ADDRESS)).json()
    second = (
        await client.post(
            "/v1/me/addresses",
            headers=member.headers,
            json={**ADDRESS, "label": "Travail", "is_default_shipping": True},
        )
    ).json()
    listed = (await client.get("/v1/me/addresses", headers=member.headers)).json()["data"]
    defaults = {a["id"]: a["is_default_shipping"] for a in listed}
    assert defaults == {first["id"]: False, second["id"]: True}


@pytest.mark.parametrize(
    "change",
    [
        {"full_name": ""},
        {"country_code": "fra"},
        {"phone_e164": "0612345678"},
        {"lat": 91},
        {"lat": 45.0, "lon": None},
        {"postal_code": "x" * 21},
    ],
)
async def test_address_invalid_422(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, change: dict[str, Any]
) -> None:
    member = await _member(sessionmaker)
    body = {**ADDRESS, **change}
    if change.get("lon", ...) is None:
        body.pop("lon")
    response = await client.post("/v1/me/addresses", headers=member.headers, json=body)
    assert response.status_code == 422


# --- Search zones --------------------------------------------------------------------------


async def test_zone_default_radius_5km(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    member = await _member(sessionmaker)
    created = await client.post("/v1/me/zones", headers=member.headers, json=ZONE)
    assert created.status_code == 201, created.text
    zone = created.json()
    assert zone["radius_km"] == 5 and zone["is_default"] is True
    assert zone["place_name"] == "Lyon 7e"
    async with sessionmaker() as db:
        radius = await db.scalar(
            text("SELECT radius_m FROM search_zones WHERE id = :id"), {"id": zone["id"]}
        )
    assert radius == 5000


@pytest.mark.parametrize("radius", [0, 3, 7, 101, 1000])
async def test_zone_radius_invalid_422(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, radius: int
) -> None:
    member = await _member(sessionmaker)
    response = await client.post(
        "/v1/me/zones", headers=member.headers, json={**ZONE, "radius_km": radius}
    )
    assert response.status_code == 422


async def test_single_default_zone_switch(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    member = await _member(sessionmaker)
    home = (await client.post("/v1/me/zones", headers=member.headers, json=ZONE)).json()
    work = (
        await client.post(
            "/v1/me/zones",
            headers=member.headers,
            json={**ZONE, "label": "Travail", "radius_km": 10},
        )
    ).json()
    assert work["is_default"] is False

    switched = await client.patch(
        f"/v1/me/zones/{work['id']}", headers=member.headers, json={"is_default": True}
    )
    assert switched.status_code == 200 and switched.json()["is_default"] is True
    zones = {
        z["id"]: z["is_default"]
        for z in (await client.get("/v1/me/zones", headers=member.headers)).json()["data"]
    }
    assert zones == {home["id"]: False, work["id"]: True}

    # Deleting the default zone hands the role to the oldest remaining one.
    assert (
        await client.delete(f"/v1/me/zones/{work['id']}", headers=member.headers)
    ).status_code == 204
    [remaining] = (await client.get("/v1/me/zones", headers=member.headers)).json()["data"]
    assert remaining["id"] == home["id"] and remaining["is_default"] is True


async def test_zone_cannot_be_undefaulted_directly(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    member = await _member(sessionmaker)
    zone = (await client.post("/v1/me/zones", headers=member.headers, json=ZONE)).json()
    response = await client.patch(
        f"/v1/me/zones/{zone['id']}", headers=member.headers, json={"is_default": False}
    )
    assert response.status_code == 422


async def test_zone_update_and_other_user_404(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    owner, intruder = await _member(sessionmaker), await _member(sessionmaker)
    zone = (await client.post("/v1/me/zones", headers=owner.headers, json=ZONE)).json()
    path = f"/v1/me/zones/{zone['id']}"
    moved = await client.patch(
        path,
        headers=owner.headers,
        json={"place_name": "Bordeaux", "lat": 44.8378, "lon": -0.5792, "radius_km": 25},
    )
    assert moved.status_code == 200
    assert (moved.json()["place_name"], moved.json()["radius_km"]) == ("Bordeaux", 25)
    assert (
        await client.patch(path, headers=intruder.headers, json={"label": "x"})
    ).status_code == 404
    assert (await client.delete(path, headers=intruder.headers)).status_code == 404
    # A new place needs its coordinates, and the reverse.
    assert (
        await client.patch(path, headers=owner.headers, json={"place_name": "Nantes"})
    ).status_code == 422


async def test_places_need_a_completed_profile(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    incomplete = await make_account(sessionmaker)
    for path in ("/v1/me/addresses", "/v1/me/zones"):
        assert (await client.get(path, headers=incomplete.headers)).status_code == 403
