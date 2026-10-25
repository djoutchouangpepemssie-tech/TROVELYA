"""No personal data in logs, error reports or traces (P1 gate, G4; GDPR, section 15).

A full first journey (magic link, profile, address, export, then an error) runs with the
production telemetry settings, and everything that would leave the process is captured: the
log lines as written, the Sentry envelopes (errors and transactions) and the OpenTelemetry
spans. None may contain the member's e-mail, link token, IP address, name, street address,
phone number or birth year.
"""

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
import sentry_sdk
import structlog
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
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.integration.identity.test_places import ADDRESS
from tests.integration.identity.test_profile import profile_form
from trovelya.core.config import Settings
from trovelya.core.csrf import CSRF_COOKIE
from trovelya.core.email import open_email
from trovelya.core.flags import FlagService
from trovelya.core.observability import instrument
from trovelya.main import create_app
from trovelya.modules.identity.service.gdpr import build_data_export
from trovelya.shared.clock import SystemClock
from trovelya.shared.ids import new_id

WEB = "https://web.example.test"
NAME = "Ambroisine Quintal"
STREET = "17 rue des Capucins"
PHONE = "+33698765432"
BIRTH_YEAR = 1937
IP = "203.0.113.77"
SENTRY_DSN = "https://public@o0.ingest.de.sentry.io/1"
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

    def everything(self) -> str:
        spans = [span.to_json() for span in self.spans.get_finished_spans()]
        return "\n".join([*self.lines, *self.envelopes, *spans])


class _Queue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[Captured]:
    found = Captured()

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
    structlog.reset_defaults()


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    engine: AsyncEngine,
    captured: Captured,
) -> Any:
    settings: Settings = make_settings(web_origin=WEB, sentry_dsn=SENTRY_DSN)
    app = create_app(settings)
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.flags = FlagService(sessionmaker, redis_client, {})
    app.state.queue = _Queue()

    # Standard library loggers (httpx, SQLAlchemy…) through the formatter the app installed.
    root = logging.getLogger()
    formatter = root.handlers[0].formatter

    class Lines(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if formatter is not None:
                captured.lines.append(formatter.format(record))

    lines = Lines()
    root.addHandler(lines)

    # Traces: what production instruments, into memory instead of the OTLP exporter.
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(captured.spans))
    instrument(app, tracer_provider=provider, engine=engine)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
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


async def test_journey_leaves_no_personal_data_in_telemetry(
    sessionmaker: async_sessionmaker[AsyncSession], client: Any, captured: Captured
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
    await http.get("/v1/csrf")
    http.headers["x-csrf-token"] = http.cookies[CSRF_COOKIE]

    # Profile, then a postal address.
    form = profile_form(display_name=NAME, birth_year=BIRTH_YEAR)
    completed = await http.post("/v1/me/complete-profile", json=form)
    assert completed.status_code == 200, completed.text
    address = {**ADDRESS, "full_name": NAME, "line1": STREET, "phone_e164": PHONE}
    assert (await http.post("/v1/me/addresses", json=address)).status_code == 201

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

    # An error report from a request that carries personal data in its address and headers.
    failed = await http.get("/v1/_debug/error", params={"email": email, "q": STREET})
    assert failed.status_code == 500
    sentry_sdk.get_client().flush()

    # Something was captured on each channel: an empty capture would prove nothing.
    assert captured.lines, "no log line"
    assert any('"type":"event"' in e.replace(" ", "") for e in captured.envelopes), "no error"
    assert any('"type":"transaction"' in e.replace(" ", "") for e in captured.envelopes)
    spans = captured.spans.get_finished_spans()
    assert any(span.attributes and "db.statement" in span.attributes for span in spans)
    assert any(span.name.startswith("POST /v1/auth/magic-link") for span in spans)

    sent = captured.everything()
    personal = {
        "e-mail": email,
        "link token": token,
        "IP address": IP,
        "name": NAME,
        "street": STREET,
        "phone": PHONE,
    }
    # The URL-encoded forms too, as in a query string.
    personal |= {
        "e-mail (encoded)": email.replace("@", "%40"),
        "street (encoded)": STREET.replace(" ", "+"),
        "street (escaped)": STREET.replace(" ", "%20"),
    }
    leaks = {label: _around(value, sent) for label, value in personal.items() if value in sent}
    assert leaks == {}
    year = re.search(rf"(?<![0-9A-Za-z.]){BIRTH_YEAR}(?![0-9A-Za-z])", sent)
    assert year is None, _around(year.group(0), sent) if year else ""


def _around(value: str, text: str) -> str:
    """Where a value was found, to tell which channel let it through."""
    at = text.index(value)
    return text[max(0, at - 200) : at + len(value) + 60].replace("\n", " ")
