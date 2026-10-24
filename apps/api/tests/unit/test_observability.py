from collections.abc import Iterator

import pytest
import sentry_sdk
from fastapi import FastAPI

from tests.conftest import make_settings
from trovelya.core.observability import configure_observability

FAKE_DSN = "https://public@o0.ingest.de.sentry.io/0"


@pytest.fixture(autouse=True)
def _reset_sentry() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    yield
    sentry_sdk.init(dsn=None)


def test_sentry_not_initialised_without_dsn() -> None:
    configure_observability(FastAPI(), make_settings())
    assert not sentry_sdk.get_client().is_active()


def test_sentry_initialised_without_personal_data() -> None:
    configure_observability(FastAPI(), make_settings(env="staging", sentry_dsn=FAKE_DSN))
    client = sentry_sdk.get_client()
    assert client.is_active()
    assert client.options["environment"] == "staging"
    collected = client.options["data_collection"]
    assert collected["user_info"] is False
    assert collected["cookies"] == {"mode": "off"}
    assert collected["http_bodies"] == []
    assert collected["url_query_params"] == {"mode": "off"}
    assert collected["stack_frame_variables"] is False
