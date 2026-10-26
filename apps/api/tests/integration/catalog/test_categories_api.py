"""`GET /v1/categories` and `GET /v1/brands` (P2-T01b)."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.catalog.service.seed import (
    load_seed,
    parse_brands,
    read_seed_file,
)
from trovelya.modules.catalog.service.seed_writer import apply_brands, apply_seed
from trovelya.modules.catalog.universes import UNIVERSE_KEYS

VERTICALS = {"vehicules", "immobilier", "services"}


@pytest.fixture(scope="module")
async def seeded(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as db:
        await apply_seed(db, load_seed())
        await apply_brands(db, parse_brands(read_seed_file("brands.yaml")))
        await db.commit()


async def _client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis, *, verticals: bool
) -> AsyncClient:
    app = create_app(make_settings())
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.flags = FlagService(sessionmaker, redis_client, {"verticals": verticals})
    client = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    )
    client.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
    return client


@pytest.fixture
async def client(
    seeded: None, sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> AsyncIterator[AsyncClient]:
    async with await _client(sessionmaker, redis_client, verticals=False) as c:
        yield c


async def test_categories_hide_verticals_when_flag_off(client: AsyncClient) -> None:
    response = await client.get("/v1/categories")
    assert response.status_code == 200
    tree = response.json()
    roots = [c["key"] for c in tree["categories"] if c["parent_key"] is None]
    assert roots == [key for key in UNIVERSE_KEYS if key not in VERTICALS]
    assert not [c for c in tree["categories"] if c["vertical"] != "goods"]


async def test_categories_show_verticals_when_flag_on(
    seeded: None, sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    async with await _client(sessionmaker, redis_client, verticals=True) as client:
        tree = (await client.get("/v1/categories")).json()
    roots = [c["key"] for c in tree["categories"] if c["parent_key"] is None]
    assert roots == list(UNIVERSE_KEYS)
    assert len(tree["categories"]) == 430


async def test_categories_parents_first_with_inherited_attributes(client: AsyncClient) -> None:
    tree = (await client.get("/v1/categories")).json()
    keys = [c["key"] for c in tree["categories"]]
    by_key = {c["key"]: c for c in tree["categories"]}
    for category in tree["categories"]:
        if category["parent_key"]:
            assert keys.index(category["parent_key"]) < keys.index(category["key"])
    dresses = by_key["mode.femme.robes"]
    assert dresses["is_leaf"] is True and by_key["mode.femme"]["is_leaf"] is False
    assert dresses["name"] == "Robes"
    assert dresses["attributes"] == [
        {"key": "color", "required": False, "filterable": True},
        {"key": "material", "required": False, "filterable": True},
        {"key": "clothing_size", "required": True, "filterable": True},
    ]
    cosmetics = by_key["beaute_bien_etre.soins_maquillage.maquillage"]
    assert cosmetics["allowed_conditions"] == ["new_with_tags", "new_without_tags"]
    assert by_key["collection.militaria.insignes"]["is_restricted"] is True


async def test_attributes_in_display_order(client: AsyncClient) -> None:
    tree = (await client.get("/v1/categories")).json()
    attributes = {a["key"]: a for a in tree["attributes"]}
    used = {a["key"] for c in tree["categories"] for a in c["attributes"]}
    assert set(attributes) == used
    sizes = [v["key"] for v in attributes["clothing_size"]["values"]]
    assert sizes == ["xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl", "xxxxl", "unique"]
    shoe = attributes["shoe_eu"]
    assert (shoe["type"], shoe["min"], shoe["max"], shoe["step"], shoe["values"]) == (
        "decimal",
        15,
        52,
        0.5,
        None,
    )


async def test_categories_cache_headers(client: AsyncClient) -> None:
    response = await client.get("/v1/categories")
    assert response.headers["cache-control"] == "public, max-age=3600"
    etag = response.headers["etag"]
    again = await client.get("/v1/categories", headers={"if-none-match": f'"x", {etag}'})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag
    other = await client.get("/v1/categories", headers={"if-none-match": '"x"'})
    assert other.status_code == 200


async def test_etag_changes_with_the_flag(
    seeded: None, sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    async with await _client(sessionmaker, redis_client, verticals=False) as off:
        etag_off = (await off.get("/v1/categories")).headers["etag"]
    async with await _client(sessionmaker, redis_client, verticals=True) as on:
        etag_on = (await on.get("/v1/categories")).headers["etag"]
    assert etag_off != etag_on


async def test_brands_autocomplete(client: AsyncClient) -> None:
    response = await client.get("/v1/brands", params={"q": "her"})
    assert response.status_code == 200
    names = [b["name"] for b in response.json()["brands"]]
    assert names[0] in {"Hermès", "Herbelin", "Herschel"}
    assert {"Hermès", "Herbelin", "Herschel"} <= set(names)
    assert len(names) <= 10


async def test_brands_tolerate_a_typo(client: AsyncClient) -> None:
    names = [b["name"] for b in (await client.get("/v1/brands?q=Adidsa")).json()["brands"]]
    assert "Adidas" in names


async def test_brands_wildcards_are_literal(client: AsyncClient) -> None:
    response = await client.get("/v1/brands", params={"q": "%%"})
    assert response.status_code == 200
    assert response.json()["brands"] == []


@pytest.mark.parametrize("q", ["a", "x" * 81])
async def test_brands_query_length(client: AsyncClient, q: str) -> None:
    assert (await client.get("/v1/brands", params={"q": q})).status_code == 422
