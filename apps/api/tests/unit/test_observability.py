from collections.abc import Iterator

import pytest
import sentry_sdk
from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from tests.conftest import make_settings
from trovelya.core.logging import REDACTED
from trovelya.core.observability import (
    RedactingSpanExporter,
    configure_observability,
    scrub_breadcrumb,
    scrub_event,
)

FAKE_DSN = "https://public@o0.ingest.de.sentry.io/0"


@pytest.fixture(autouse=True)
def _reset_sentry() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    yield
    # `init(dsn=None)` would leave an active client behind: no client at all.
    for scope in (
        sentry_sdk.get_global_scope(),
        sentry_sdk.get_isolation_scope(),
        sentry_sdk.get_current_scope(),
    ):
        scope.set_client(None)


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


def test_access_log_breadcrumbs_are_dropped() -> None:
    crumb = {"category": "uvicorn.access", "message": '92.170.253.181:0 - "GET / HTTP/1.1" 200'}
    assert scrub_breadcrumb(crumb, {}) is None


def test_breadcrumbs_and_events_are_redacted() -> None:
    crumb = scrub_breadcrumb(
        {"category": "app", "message": "contact jean.dupont@gmail.com from 92.170.253.181"}, {}
    )
    assert crumb is not None
    assert "jean.dupont@gmail.com" not in str(crumb)
    assert "92.170.253.181" not in str(crumb)
    event = scrub_event(
        {"spans": [{"description": "ZADD rl:anon:92.170.253.181", "data": {"ip": "1.2.3.4"}}]}, {}
    )
    assert "92.170.253.181" not in str(event)
    assert "1.2.3.4" not in str(event)


def test_outgoing_query_strings_never_reach_sentry() -> None:
    """The httpx spans of a transaction (a geocoded address) and its breadcrumbs."""
    event = {
        "spans": [
            {
                "op": "http.client",
                "description": "GET https://data.geopf.fr/geocodage/search",
                "data": {
                    "url": "https://data.geopf.fr/geocodage/search?q=17+rue+des+Capucins",
                    "http.query": "q=17+rue+des+Capucins&limit=5",
                    "http.fragment": "x",
                },
            }
        ],
        "request": {"url": "https://api.test/v1/geo/search?q=17", "query_string": "q=17"},
    }
    sent = str(scrub_event(event, {}))
    assert "Capucins" not in sent and "q=17" not in sent
    crumb = {"category": "httplib", "data": {"url": "https://x.test/a?q=17+rue+des+Capucins"}}
    assert "Capucins" not in str(scrub_breadcrumb(crumb, {}))


def test_database_error_messages_never_reach_sentry() -> None:
    message = "invalid input for query argument $1: 'Ambroisine Quintal'"
    event = {
        "exception": {
            "values": [
                {"type": "DataError", "module": "asyncpg.exceptions", "value": message},
                {"type": "DBAPIError", "module": "sqlalchemy.exc", "value": message},
                {"type": "DebugError", "module": "trovelya.core.debug_routes", "value": "kept"},
            ]
        }
    }
    values = scrub_event(event, {})["exception"]["values"]
    assert [value["value"] for value in values] == [REDACTED, REDACTED, "kept"]


def test_spans_go_out_redacted_whole() -> None:
    """Attributes set late, captured headers, exceptions and status: all redacted on export."""
    exported = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(exported)))
    with provider.get_tracer("test").start_as_current_span("GET /v1/geo/search") as span:
        span.set_attribute("http.url", "https://api.test/v1/geo/search?q=17+rue+des+Capucins")
        span.set_attribute("url.query", "q=17+rue+des+Capucins")
        span.set_attribute("http.request.header.cookie", ["__Host-trv_session=secret"])
        span.set_attribute("client.address", "203.0.113.77")
        try:
            raise ValueError("invalid input for query argument $1: 'Ambroisine Quintal'")
        except ValueError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
    [sent] = exported.get_finished_spans()
    text = sent.to_json()
    for personal in ("Capucins", "secret", "203.0.113.77", "Ambroisine"):
        assert personal not in text, personal
    assert sent.attributes is not None
    assert sent.attributes["http.url"] == "https://api.test/v1/geo/search"
    [event] = sent.events
    assert event.attributes is not None and event.attributes["exception.type"] == "ValueError"
