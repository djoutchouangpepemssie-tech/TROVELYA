"""FastAPI application factory. Run with: uvicorn --factory trovelya.main:create_app"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI

from trovelya.core import db, debug_routes, redis, testing_routes
from trovelya.core.config import Settings, get_settings
from trovelya.core.csrf import CsrfMiddleware
from trovelya.core.csrf import router as csrf_router
from trovelya.core.errors import install_error_handlers
from trovelya.core.health import ReadinessCheck
from trovelya.core.health import router as health_router
from trovelya.core.idempotency import IdempotencyMiddleware
from trovelya.core.logging import configure_logging
from trovelya.core.middleware import RequestIdMiddleware
from trovelya.core.observability import configure_observability
from trovelya.core.ratelimit import AnonymousRateLimitMiddleware
from trovelya.modules.identity.api import router as identity_router
from trovelya.shared.clock import SystemClock


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
        redis_client = redis.make_redis(settings.redis_url)

        async def database_check() -> None:
            await db.ping(engine)

        async def redis_check() -> None:
            await redis.ping(redis_client)

        app.state.readiness_checks = {"database": database_check, "redis": redis_check}
        app.state.sessionmaker = db.make_sessionmaker(engine)
        app.state.redis = redis_client
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
    if settings.env != "production":
        app.include_router(debug_routes.router)
    if settings.env in {"local", "test"}:
        app.include_router(testing_routes.router)
    return app
