"""Geocoding with the IGN Géoplateforme (E10: the former API Adresse moved there in 2026).

`https://data.geopf.fr/geocodage/{search,reverse}` answers GeoJSON in the format of the Base
Adresse Nationale. Only the typed text (or the coordinates) is sent: no cookie, no user
identifier. A slow or failing service raises `GeocoderUnavailableError` after 2 seconds.
"""

import math
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

BASE_URL = "https://data.geopf.fr/geocodage"
TIMEOUT_S = 2.0
_ARRONDISSEMENT = " Arrondissement"


class GeocoderUnavailableError(Exception):
    """The geocoding service did not answer in time or answered garbage."""


@dataclass(frozen=True, slots=True)
class Place:
    label: str
    city: str
    postal_code: str
    district: str | None  # Paris, Lyon and Marseille arrondissements: "Lyon 7e"
    country_code: str
    lat: float
    lon: float

    @property
    def place_name(self) -> str:
        """Short name shown for a search zone: the arrondissement, else the city."""
        return self.district or self.city


class Geocoder(Protocol):
    async def search(self, q: str, *, limit: int = 5) -> list[Place]: ...

    async def reverse(self, lat: float, lon: float) -> Place | None: ...


def _place(feature: dict[str, Any]) -> Place | None:
    properties: dict[str, Any] = feature.get("properties") or {}
    city, postcode = properties.get("city"), properties.get("postcode")
    try:
        lon, lat = feature["geometry"]["coordinates"][:2]
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(city, str) or not isinstance(postcode, str):
        return None
    district = properties.get("district")
    return Place(
        label=str(properties.get("label") or city),
        city=city,
        postal_code=postcode,
        district=district.removesuffix(_ARRONDISSEMENT) if isinstance(district, str) else None,
        country_code="FR",
        lat=float(lat),
        lon=float(lon),
    )


class GeoplateformeGeocoder:
    def __init__(self, client: httpx.AsyncClient, *, base_url: str = BASE_URL) -> None:
        self._client = client
        self._base_url = base_url

    async def _features(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            response = await self._client.get(
                f"{self._base_url}/{path}", params=params, timeout=TIMEOUT_S
            )
            response.raise_for_status()
            features = response.json()["features"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise GeocoderUnavailableError(type(exc).__name__) from exc
        return [f for f in features if isinstance(f, dict)]

    async def search(self, q: str, *, limit: int = 5) -> list[Place]:
        features = await self._features(
            "search", {"q": q, "limit": str(limit), "autocomplete": "1"}
        )
        return [place for f in features if (place := _place(f)) is not None]

    async def reverse(self, lat: float, lon: float) -> Place | None:
        features = await self._features("reverse", {"lat": str(lat), "lon": str(lon), "limit": "1"})
        return next((place for f in features if (place := _place(f)) is not None), None)


_FAKE_PLACES = (
    Place("Paris 11e Arrondissement", "Paris", "75011", "Paris 11e", "FR", 48.8590, 2.3800),
    Place("Lyon 7e Arrondissement", "Lyon", "69007", "Lyon 7e", "FR", 45.7450, 4.8420),
    Place("Bordeaux", "Bordeaux", "33000", None, "FR", 44.8378, -0.5792),
)


class FakeGeocoder:
    """Tests and local development: three places, no network."""

    async def search(self, q: str, *, limit: int = 5) -> list[Place]:
        needle = q.strip().lower()
        return [p for p in _FAKE_PLACES if needle in p.label.lower()][:limit]

    async def reverse(self, lat: float, lon: float) -> Place | None:
        return min(_FAKE_PLACES, key=lambda p: math.hypot(p.lat - lat, p.lon - lon))
