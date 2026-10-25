"""No personal data in logs, error reports or traces (P1 gate, G4; GDPR, section 15).

A full first journey runs with the production telemetry options (only `env` is "test", so every
transaction is sampled): magic link, profile, address, zone, place search (the real geocoder
adapter, over a mock transport), GDPR export built by the worker's code and downloaded, then
two errors (an unhandled one, and an SQL error carrying a name). Everything that would leave
the process is captured: log lines as written, the Sentry envelopes (errors, transactions and
their spans, breadcrumbs), the OpenTelemetry spans as exported (SQL, Redis and requests), and
whatever reaches stdout or stderr. None may contain the member's e-mail, link or session
token, IP address, name, street, postcode, phone number, coordinates or birth year.
"""

import json
import logging
import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import (  # pyright: ignore[reportMissingTypeStubs]
    SQLAlchemyInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from redis.asyncio import Redis
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_places import ADDRESS, ZONE
from tests.integration.identity.test_profile import profile_form
from trovelya.core.config import Settings
from trovelya.core.csrf import CSRF_COOKIE, SESSION_COOKIE
from trovelya.core.email import open_email
from trovelya.core.flags import FlagService
from trovelya.core.observability import RedactingSpanExporter, instrument, trace_engine
from trovelya.main import create_app
from trovelya.modules.identity.adapters.geocoder import GeoplateformeGeocoder
from trovelya.modules.identity.service.gdpr import build_data_export
from trovelya.shared.clock import SystemClock
from trovelya.shared.ids import new_id

WEB = "https://web.example.test"
NAME = "Ambroisine Quintal"
STREET = "17 rue des Capucins"
POSTCODE = "69001"
PHONE = "+33698765432"
LAT, LON = 45.767123, 4.833987
BIRTH_YEAR = 1937
IP = "203.0.113.77"
SENTRY_DSN = "https://public@o0.ingest.de.sentry.io/1"
GEOCODER_SAMPLE = json.loads(
    (Path(__file__).parents[2] / "fixtures/geoplateforme_search.json").read_text()
)
# The printing methods of structlog's PrintLogger (aliases of `msg`, bound at class creation).
_PRINT_METHODS = (
    "msg", "log", "debug", "info", "warning", "warn", "error", "err", "critical", "fatal",
    "exception", "failure",
)  # fmt: skip


@dataclass
class Captured:
    lines: list[str] = field(default_factory=list[str])
    envelopes: list[str] = field(default_factory=list[str])
    spans: InMemorySpanExporter = field(default_factory=InMemorySpanExporter)

    def everything(self, *streams: str) -> str:
        spans = [span.to_json() for span in self.spans.get_finished_spans()]
        return "\n".join([*self.lines, *self.envelopes, *spans, *streams])


class _Queue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[Captured]:
    found = Captured()
    logging_config = structlog.get_config()

    # Logs: every line as written, also by the module loggers cached by earlier tests.
    original = structlog.PrintLogger.msg

    def record(self: structlog.PrintLogger, message: str) -> None:
        found.lines.append(message)
        original(self, message)

    for name in _PRINT_METHODS:
        monkeypatch.setattr(structlog.PrintLogger, name, record)

    # Sentry: the real options of `configure_observability`, with an in-memory transport.
    class Recording(Transport):
        def capture_envelope(self, envelope: Envelope) -> None:
            found.envelopes.append(envelope.serialize().decode("utf-8", "replace"))

    sentry_init = sentry_sdk.init

    def init(*args: Any, **kwargs: Any) -> Any:
        return sentry_init(*args, **kwargs, transport=Recording)

    monkeypatch.setattr(sentry_sdk, "init", init)
    yield found
    sentry_sdk.get_client().close()
    # No client for the tests that follow (`init(dsn=None)` would leave an active one).
    for scope in (
        sentry_sdk.get_global_scope(),
        sentry_sdk.get_isolation_scope(),
        sentry_sdk.get_current_scope(),
    ):
        scope.set_client(None)
    structlog.configure(**logging_config)


def _geocoder() -> GeoplateformeGeocoder:
    def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=GEOCODER_SAMPLE)

    return GeoplateformeGeocoder(httpx.AsyncClient(transport=httpx.MockTransport(answer)))


async def _sql_error(request: Request) -> None:
    """A query that fails with personal data among its parameters."""
    async with request.app.state.sessionmaker() as db:
        await db.execute(text("SELECT CAST(:value AS integer)"), {"value": NAME})


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    engine: AsyncEngine,
    captured: Captured,
) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    settings: Settings = make_settings(web_origin=WEB, sentry_dsn=SENTRY_DSN)
    app = create_app(settings)
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    app.state.queue = _Queue()
    app.state.geocoder = _geocoder()
    app.add_api_route("/v1/_pii/sql-error", _sql_error)

    # Standard library loggers (httpx, uvicorn…) through the handler the app installed.
    root = logging.getLogger()
    installed = root.handlers[0]

    class Lines(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if installed.filter(record) and installed.formatter is not None:
                captured.lines.append(installed.formatter.format(record))

    lines = Lines()
    root.addHandler(lines)

    # Traces: production's instrumentation and redaction, exported into memory.
    assert not RedisInstrumentor().is_instrumented_by_opentelemetry
    assert not SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(captured.spans)))
    instrument(app, tracer_provider=provider)
    trace_engine(engine, tracer_provider=provider)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False, client=(IP, 51234)),
            base_url="https://test",
        ) as c:
            c.headers.update(
                {
                    "x-trv-proxy-secret": TEST_PROXY_SECRET,
                    "x-trv-client-ip": IP,
                    # As the web relay forwards them (lib/server-api.ts).
                    "x-forwarded-for": IP,
                    "x-real-ip": IP,
                    "user-agent": "Mozilla/5.0 (test)",
                }
            )
            yield app, c
    finally:
        root.removeHandler(lines)
        FastAPIInstrumentor.uninstrument_app(app)
        SQLAlchemyInstrumentor().uninstrument()  # pyright: ignore[reportUnknownMemberType]
        RedisInstrumentor().uninstrument()  # pyright: ignore[reportUnknownMemberType]
        provider.shutdown()


def _token(queue: _Queue, settings: Settings) -> str:
    message = open_email(queue.jobs[-1][1][0], settings=settings)
    found = re.search(r"#token=([A-Za-z0-9_-]+)", message.text)
    assert found is not None
    return found.group(1)


def _envelopes_of(captured: Captured, kind: str) -> list[str]:
    return [e for e in captured.envelopes if f'"type":"{kind}"' in e.replace(" ", "")]


async def test_journey_leaves_no_personal_data_in_telemetry(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: tuple[FastAPI, AsyncClient],
    captured: Captured,
    capfd: pytest.CaptureFixture[str],
) -> None:
    app, http = client
    settings: Settings = app.state.settings
    queue: _Queue = app.state.queue
    email = f"ambroisine.{new_id().hex[-10:]}@exemple-perso.fr"

    # Sign-up by magic link.
    assert (await http.post("/v1/auth/magic-link", json={"email": email})).status_code == 202
    token = _token(queue, settings)
    verified = await http.post("/v1/auth/magic-link/verify", json={"token": token})
    assert verified.status_code == 200, verified.text
    session = http.cookies[SESSION_COOKIE]
    await http.get("/v1/csrf")
    http.headers["x-csrf-token"] = http.cookies[CSRF_COOKIE]

    # Profile, address, zone, and the place searches of the welcome steps.
    form = profile_form(display_name=NAME, birth_year=BIRTH_YEAR)
    completed = await http.post("/v1/me/complete-profile", json=form)
    assert completed.status_code == 200, completed.text
    address = {
        **ADDRESS,
        "full_name": NAME,
        "line1": STREET,
        "postal_code": POSTCODE,
        "phone_e164": PHONE,
        "lat": LAT,
        "lon": LON,
    }
    assert (await http.post("/v1/me/addresses", json=address)).status_code == 201
    zone = {**ZONE, "lat": LAT, "lon": LON}
    assert (await http.post("/v1/me/zones", json=zone)).status_code == 201
    found = await http.get("/v1/geo/search", params={"q": f"{STREET} {POSTCODE}"})
    assert found.status_code == 200, found.text
    assert (await http.get("/v1/geo/reverse", params={"lat": LAT, "lon": LON})).status_code == 200

    # GDPR export: asked, built by the worker's code, downloaded.
    export = await http.post("/v1/me/data-export")
    assert export.status_code == 202, export.text
    request_id = export.json()["request_id"]
    built = await build_data_export(
        sessionmaker, UUID(request_id), settings=settings, clock=SystemClock(), queue=queue
    )
    assert built
    archive = await http.get(f"/v1/me/data-export/{request_id}/download")
    assert archive.status_code == 200

    # Errors: one from a request carrying personal data in its address, one from SQL.
    failed = await http.get("/v1/_debug/error", params={"email": email, "q": STREET})
    assert failed.status_code == 500
    assert (await http.get("/v1/_pii/sql-error")).status_code == 500
    sentry_sdk.get_client().flush()

    # Every channel was exercised: an empty capture would prove nothing.
    assert captured.lines, "no log line"
    assert len(_envelopes_of(captured, "event")) >= 2, "no error report"
    assert _envelopes_of(captured, "transaction"), "no transaction"
    assert any("data.geopf.fr" in e for e in captured.envelopes), "no outgoing request span"
    scopes = {
        span.instrumentation_scope.name
        for span in captured.spans.get_finished_spans()
        if span.instrumentation_scope is not None
    }
    assert {
        "opentelemetry.instrumentation.sqlalchemy",
        "opentelemetry.instrumentation.redis",
        "opentelemetry.instrumentation.fastapi",
    } <= scopes, scopes

    streams = capfd.readouterr()
    sent = captured.everything(streams.out, streams.err)
    personal = {
        "e-mail": email,
        "e-mail (encoded)": email.replace("@", "%40"),
        "link token": token,
        "session token": session,
        "IP address": IP,
        "name": NAME,
        "street": STREET,
        "street (encoded)": STREET.replace(" ", "+"),
        "street (escaped)": STREET.replace(" ", "%20"),
        "phone": PHONE,
        "phone (encoded)": PHONE.replace("+", "%2B"),
        "latitude": str(LAT),
        "longitude": str(LON),
    }
    leaks = {label: _around(value, sent) for label, value in personal.items() if value in sent}
    assert leaks == {}
    for label, value in {"postcode": POSTCODE, "birth year": str(BIRTH_YEAR)}.items():
        number = re.search(rf"(?<![0-9A-Za-z.]){value}(?![0-9A-Za-z])", sent)
        assert number is None, f"{label}: {_around(number.group(0), sent) if number else ''}"


def _around(value: str, text: str) -> str:
    """Where a value was found, to tell which channel let it through."""
    at = text.index(value)
    return text[max(0, at - 200) : at + len(value) + 60].replace("\n", " ")
