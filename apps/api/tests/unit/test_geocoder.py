"""Géoplateforme geocoder adapter (P1-T06a, E10)."""

import json
from pathlib import Path

import httpx
import pytest

from trovelya.modules.identity.adapters.geocoder import (
    FakeGeocoder,
    GeocoderUnavailableError,
    GeoplateformeGeocoder,
    Place,
)

SAMPLE = json.loads(
    (Path(__file__).parent.parent / "fixtures/geoplateforme_search.json").read_text()
)


def _geocoder(handler: httpx.MockTransport) -> GeoplateformeGeocoder:
    return GeoplateformeGeocoder(httpx.AsyncClient(transport=handler))


async def test_geoplateforme_parsing() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=SAMPLE)

    places = await _geocoder(httpx.MockTransport(handler)).search("12 rue de marseille", limit=5)
    assert places == [
        Place(
            label="12 Rue de Marseille 69007 Lyon",
            city="Lyon",
            postal_code="69007",
            district="Lyon 7e",
            country_code="FR",
            lat=45.744212,
            lon=4.842374,
        ),
        Place(
            label="Bordeaux",
            city="Bordeaux",
            postal_code="33000",
            district=None,
            country_code="FR",
            lat=44.851895,
            lon=-0.587877,
        ),
    ]
    assert places[0].place_name == "Lyon 7e" and places[1].place_name == "Bordeaux"
    [request] = seen
    assert str(request.url).startswith("https://data.geopf.fr/geocodage/search?")
    assert dict(request.url.params) == {
        "q": "12 rue de marseille",
        "limit": "5",
        "autocomplete": "1",
    }
    # Only the typed text leaves: no cookie, no user identifier, no IP header.
    assert "cookie" not in request.headers and "x-forwarded-for" not in request.headers


async def test_reverse_returns_first_place_or_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/geocodage/reverse"
        assert dict(request.url.params) == {"lat": "45.75", "lon": "4.84", "limit": "1"}
        return httpx.Response(200, json=SAMPLE)

    place = await _geocoder(httpx.MockTransport(handler)).reverse(45.75, 4.84)
    assert place is not None and place.city == "Lyon"

    empty = _geocoder(httpx.MockTransport(lambda _: httpx.Response(200, json={"features": []})))
    assert await empty.reverse(0.0, 0.0) is None


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("down"),
        httpx.Response(503),
        httpx.Response(200, text="<html>"),
    ],
)
async def test_failures_raise_unavailable(failure: Exception | httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(failure, Exception):
            raise failure
        return failure

    with pytest.raises(GeocoderUnavailableError):
        await _geocoder(httpx.MockTransport(handler)).search("paris")


async def test_fake_geocoder() -> None:
    fake = FakeGeocoder()
    assert [p.place_name for p in await fake.search("lyon")] == ["Lyon 7e"]
    assert len(await fake.search("e", limit=2)) == 2
    nearest = await fake.reverse(48.86, 2.38)
    assert nearest is not None and nearest.place_name == "Paris 11e"
