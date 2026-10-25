"""Error tracking (Sentry, EU region) and OpenTelemetry traces and metrics (section 16.4).

Both are optional: without SENTRY_DSN or OTEL_EXPORTER_OTLP_ENDPOINT nothing is sent.
"""

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
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span
from sqlalchemy.ext.asyncio import AsyncEngine

from trovelya.core.config import Settings
from trovelya.core.logging import REDACTED, redact_value

meter = metrics.get_meter("trovelya")
# Updated by the outbox relay; a growing value means events are not being published.
outbox_oldest_unpublished_seconds = meter.create_gauge(
    "trovelya_outbox_oldest_unpublished_seconds",
    unit="s",
    description="Age of the oldest outbox event not yet published",
)


# Access log lines carry the client address and add nothing to an error report.
_DROPPED_BREADCRUMB_CATEGORIES = frozenset({"uvicorn.access"})


def scrub_breadcrumb(crumb: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Same redaction as the logs, applied before a breadcrumb leaves the process."""
    if crumb.get("category") in _DROPPED_BREADCRUMB_CATEGORIES:
        return None
    return cast("dict[str, Any]", redact_value(crumb))


def scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Same redaction as the logs, applied to errors and transactions (span descriptions too)."""
    return cast("dict[str, Any]", redact_value(event))


# Span attributes holding the request address: its query string can carry personal data
# (an address searched, an e-mail), so it never leaves the process.
_URL_ATTRIBUTES = frozenset({"http.url", "http.target", "url.full"})
_QUERY_ATTRIBUTES = frozenset({"url.query"})


def scrub_server_span(span: Span, _scope: dict[str, Any]) -> None:
    """Request spans: no query string, and the logs' redaction (e-mails, IP addresses…)."""
    attributes = getattr(span, "attributes", None)
    if not span.is_recording() or not attributes:
        return
    for key, value in list(cast("dict[str, object]", dict(attributes)).items()):
        if not isinstance(value, str):
            continue
        if key in _QUERY_ATTRIBUTES:
            clean = REDACTED
        else:
            clean = str(redact_value(value.split("?", 1)[0] if key in _URL_ATTRIBUTES else value))
        if clean != value:
            span.set_attribute(key, clean)


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
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)
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


def instrument(
    app: FastAPI | None,
    *,
    tracer_provider: TracerProvider | None = None,
    engine: AsyncEngine | None = None,
) -> None:
    """What is traced: requests, SQL and Redis. Without `tracer_provider`, the global one;
    without `engine`, every engine created afterwards (the telemetry test passes its own)."""
    if app is not None:
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,ready",
            tracer_provider=tracer_provider,
            server_request_hook=scrub_server_span,
        )
    SQLAlchemyInstrumentor().instrument(  # pyright: ignore[reportUnknownMemberType]
        tracer_provider=tracer_provider,
        **({"engine": engine.sync_engine} if engine is not None else {}),
    )
    RedisInstrumentor().instrument(  # pyright: ignore[reportUnknownMemberType]
        tracer_provider=tracer_provider
    )


def configure_observability(
    app: FastAPI | None, settings: Settings, *, service_name: str = "trovelya-api"
) -> None:
    _init_sentry(settings)
    _init_opentelemetry(app, settings, service_name)
