"""FastAPI application factory. Run with: uvicorn --factory trovelya.main:create_app"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

import httpx
from arq.connections import ArqRedis
from fastapi import FastAPI

from trovelya.core import db, debug_routes, redis, testing_routes
from trovelya.core.config import Settings, get_settings
from trovelya.core.csrf import CsrfMiddleware
from trovelya.core.csrf import router as csrf_router
from trovelya.core.errors import install_error_handlers
from trovelya.core.flags import FlagService
from trovelya.core.health import ReadinessCheck
from trovelya.core.health import router as health_router
from trovelya.core.idempotency import IdempotencyMiddleware
from trovelya.core.logging import configure_logging
from trovelya.core.middleware import RequestIdMiddleware
from trovelya.core.observability import configure_observability, trace_engine
from trovelya.core.ratelimit import AnonymousRateLimitMiddleware
from trovelya.modules.catalog.api import router as catalog_router
from trovelya.modules.identity.adapters.geocoder import (
    FakeGeocoder,
    Geocoder,
    GeoplateformeGeocoder,
)
from trovelya.modules.identity.adapters.oidc import (
    AppleProvider,
    OidcProvider,
    apple_config,
    google_config,
)
from trovelya.modules.identity.adapters.turnstile import AlwaysPass, TurnstileVerifier
from trovelya.modules.identity.api import router as identity_router
from trovelya.modules.identity.api.testing import router as identity_testing_router
from trovelya.modules.media.adapters.storage import storage_from_settings
from trovelya.modules.media.api import router as media_router  # registers its GDPR exporter too
from trovelya.shared.clock import SystemClock


def _oidc_providers(settings: Settings) -> dict[str, OidcProvider]:
    # Callbacks go through the web relay, so the cookies stay first-party (ADR-0015).
    callback = f"{settings.web_origin.rstrip('/')}/api/v1/auth/oauth/{{}}/callback"
    providers: dict[str, OidcProvider] = {}
    if settings.oauth_google_client_id and settings.oauth_google_client_secret:
        config = google_config(
            client_id=settings.oauth_google_client_id,
            client_secret=settings.oauth_google_client_secret.get_secret_value(),
            redirect_uri=callback.format("google"),
        )
        providers["google"] = OidcProvider(config, httpx.AsyncClient())
    if (
        settings.oauth_apple_client_id
        and settings.oauth_apple_team_id
        and settings.oauth_apple_key_id
        and settings.oauth_apple_private_key
    ):
        providers["apple"] = AppleProvider(
            apple_config(
                client_id=settings.oauth_apple_client_id, redirect_uri=callback.format("apple")
            ),
            httpx.AsyncClient(),
            team_id=settings.oauth_apple_team_id,
            key_id=settings.oauth_apple_key_id,
            private_key=settings.oauth_apple_private_key.get_secret_value(),
        )
    return providers


def _geocoder(settings: Settings) -> Geocoder:
    if settings.geocoder_provider == "fake":
        return FakeGeocoder()
    return GeoplateformeGeocoder(httpx.AsyncClient())


def create_app(
    settings: Settings | None = None,
    readiness_checks: Mapping[str, ReadinessCheck] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if readiness_checks is not None:
            app.state.readiness_checks = readiness_checks
            yield
            return
        engine = db.make_engine(settings.database_url)
        trace_engine(engine)
        redis_client = redis.make_redis(settings.redis_url)

        async def database_check() -> None:
            await db.ping(engine)

        async def redis_check() -> None:
            await redis.ping(redis_client)

        app.state.readiness_checks = {"database": database_check, "redis": redis_check}
        app.state.sessionmaker = db.make_sessionmaker(engine)
        app.state.redis = redis_client
        app.state.flags = FlagService(
            app.state.sessionmaker, redis_client, settings.feature_flags_default
        )
        # Job queue for the worker (e-mails…), on the same Redis connection pool.
        app.state.queue = ArqRedis(connection_pool=redis_client.connection_pool)
        try:
            yield
        finally:
            await redis_client.aclose()
            await engine.dispose()

    is_public_docs = settings.env != "production"
    app = FastAPI(
        title="TROVÉLYA API",
        version="0.0.0",
        lifespan=lifespan,
        docs_url="/docs" if is_public_docs else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.clock = SystemClock()
    app.state.oidc = _oidc_providers(settings)
    app.state.geocoder = _geocoder(settings)
    app.state.storage = storage_from_settings(settings)
    app.state.captcha = (
        TurnstileVerifier(
            secret=settings.turnstile_secret_key.get_secret_value(), client=httpx.AsyncClient()
        )
        if settings.turnstile_secret_key is not None
        else AlwaysPass()
    )
    configure_observability(app, settings)
    app.state.readiness_checks = readiness_checks or {}
    install_error_handlers(app)
    # Starlette runs the last added middleware first: request id → rate limit → CSRF →
    # idempotency → routes.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(CsrfMiddleware, secret=settings.secret_key.get_secret_value())
    app.add_middleware(
        AnonymousRateLimitMiddleware,
        per_minute=settings.rate_limit_anonymous_per_minute,
        secret=settings.secret_key.get_secret_value(),
        proxy_secret=settings.proxy_shared_secret.get_secret_value(),
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(csrf_router)
    app.include_router(identity_router)
    app.include_router(catalog_router)
    app.include_router(media_router)
    if settings.env != "production":
        app.include_router(debug_routes.router)
    if settings.env in {"local", "test"}:
        app.include_router(testing_routes.router)
        app.include_router(identity_testing_router)
    return app
