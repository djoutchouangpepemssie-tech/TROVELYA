"""Error tracking (Sentry, EU region) and OpenTelemetry traces and metrics (section 16.4).

Both are optional: without SENTRY_DSN or OTEL_EXPORTER_OTLP_ENDPOINT nothing is sent.
"""

from collections.abc import Mapping, Sequence
from typing import Any, cast

import sentry_sdk
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import (  # pyright: ignore[reportMissingTypeStubs]
    SQLAlchemyInstrumentor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Status
from sqlalchemy.ext.asyncio import AsyncEngine

from trovelya.core.config import Settings
from trovelya.core.logging import REDACTED, is_database_error, redact_value

meter = metrics.get_meter("trovelya")
# Updated by the outbox relay; a growing value means events are not being published.
outbox_oldest_unpublished_seconds = meter.create_gauge(
    "trovelya_outbox_oldest_unpublished_seconds",
    unit="s",
    description="Age of the oldest outbox event not yet published",
)


# Set once OpenTelemetry is configured: engines are traced only then.
_tracing = False

# Access log lines carry the client address and add nothing to an error report.
_DROPPED_BREADCRUMB_CATEGORIES = frozenset({"uvicorn.access"})


# Where a query string travels: it can carry personal data (an address searched, an e-mail),
# so it never leaves the process. URL values lose it; query values are masked.
_URL_KEYS = frozenset({"url", "http.url", "http.target", "url.full"})
_QUERY_KEYS = frozenset({"query_string", "http.query", "http.fragment", "url.query"})


def _without_queries(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {
            key: REDACTED
            if key in _QUERY_KEYS
            else item.split("?", 1)[0]
            if key in _URL_KEYS and isinstance(item, str)
            else _without_queries(item)
            for key, item in mapping.items()
        }
    if isinstance(value, list | tuple):
        return [_without_queries(item) for item in cast("list[object] | tuple[object, ...]", value)]
    return value


def scrub_telemetry(value: object) -> object:
    """The logs' redaction (sensitive keys, e-mails, IP addresses…), without query strings."""
    return redact_value(_without_queries(value))


def scrub_breadcrumb(crumb: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Same redaction as the logs, applied before a breadcrumb leaves the process."""
    if crumb.get("category") in _DROPPED_BREADCRUMB_CATEGORIES:
        return None
    return cast("dict[str, Any]", scrub_telemetry(crumb))


def scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Same redaction as the logs, applied to errors and transactions (their spans too, such
    as an outgoing request's `http.query`). A database error's message is withheld: the
    driver puts the query's values in it."""
    cleaned = cast("dict[str, Any]", scrub_telemetry(event))
    exception = cleaned.get("exception")
    if isinstance(exception, Mapping):
        values = cast("list[Any]", cast("Mapping[str, Any]", exception).get("values") or [])
        for value in values:
            if isinstance(value, dict):
                entry = cast("dict[str, Any]", value)
                if is_database_error(str(entry.get("module") or "")):
                    entry["value"] = REDACTED
    return cleaned


class RedactingSpanExporter(SpanExporter):
    """Every span, once finished, goes out redacted: its name, attributes (those set at the
    response too, and captured headers such as `cookie`), events and status. A hook at the
    start of a span would miss what is added afterwards.

    Exceptions keep their type only: a message or a stack trace can carry anything (a
    database driver quotes the values of a failed query), and Sentry reports errors."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_redacted(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


def _attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    cleaned = cast("dict[str, Any]", scrub_telemetry(dict(attributes or {})))
    # OpenTelemetry attribute values are scalars or sequences of scalars: keep them so.
    return {
        key: tuple(cast("list[object]", value)) if isinstance(value, list) else value
        for key, value in cleaned.items()
    }


_EXCEPTION_DETAILS = ("exception.message", "exception.stacktrace")


def _event_attributes(event: Event) -> dict[str, Any]:
    attributes = _attributes(event.attributes)
    if event.name == "exception":
        attributes.update({key: REDACTED for key in _EXCEPTION_DETAILS if key in attributes})
    return attributes


def _redacted(span: ReadableSpan) -> ReadableSpan:
    status = span.status
    description = status.description
    return ReadableSpan(
        name=str(redact_value(span.name)),
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=_attributes(span.attributes),
        events=[
            Event(event.name, _event_attributes(event), event.timestamp) for event in span.events
        ],
        links=span.links,
        kind=span.kind,
        status=Status(status.status_code, REDACTED) if description else status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def _init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        # GDPR: no user identity, IP, cookies, bodies, query strings, SQL parameters or local
        # variables are sent; of the request headers, only technical ones.
        data_collection={
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {
                "request": {"mode": "allowlist", "terms": ["x-request-id", "content-type"]}
            },
            "http_bodies": [],
            "url_query_params": {"mode": "off"},
            "database_query_data": False,
            "stack_frame_variables": False,
        },
        traces_sample_rate=0.1 if settings.env == "production" else 1.0,
        before_breadcrumb=scrub_breadcrumb,  # pyright: ignore[reportArgumentType]
        before_send=scrub_event,  # pyright: ignore[reportArgumentType]
        before_send_transaction=scrub_event,  # pyright: ignore[reportArgumentType]
    )


def _init_opentelemetry(app: FastAPI | None, settings: Settings, service_name: str) -> None:
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return
    resource = Resource.create(
        {"service.name": service_name, "deployment.environment": settings.env}
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            RedactingSpanExporter(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
        )
    )
    trace.set_tracer_provider(tracer_provider)
    global _tracing  # once per process, at start-up
    _tracing = True
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=f"{endpoint.rstrip('/')}/v1/metrics")
                )
            ],
        )
    )
    instrument(app)


def instrument(app: FastAPI | None, *, tracer_provider: TracerProvider | None = None) -> None:
    """What is traced: requests and Redis (SQL through `trace_engine`). Without
    `tracer_provider`, the global one."""
    if app is not None:
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="health,ready", tracer_provider=tracer_provider
        )
    RedisInstrumentor().instrument(  # pyright: ignore[reportUnknownMemberType]
        tracer_provider=tracer_provider
    )


def trace_engine(engine: AsyncEngine, *, tracer_provider: TracerProvider | None = None) -> None:
    """SQL statements (never their parameters) of this engine, when tracing is on. The
    instrumentation declares SQLAlchemy below 2.1, but works with it: its check is skipped
    (the telemetry test proves that statements are traced)."""
    if tracer_provider is None and not _tracing:
        return
    SQLAlchemyInstrumentor().instrument(  # pyright: ignore[reportUnknownMemberType]
        engine=engine.sync_engine, tracer_provider=tracer_provider, skip_dep_check=True
    )


def configure_observability(
    app: FastAPI | None, settings: Settings, *, service_name: str = "trovelya-api"
) -> None:
    _init_sentry(settings)
    _init_opentelemetry(app, settings, service_name)
