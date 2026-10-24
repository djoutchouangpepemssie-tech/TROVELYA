"""FastAPI application factory. Run with: uvicorn --factory trovelya.main:create_app"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI

from trovelya.core import db, redis
from trovelya.core.config import Settings, get_settings
from trovelya.core.errors import install_error_handlers
from trovelya.core.health import ReadinessCheck
from trovelya.core.health import router as health_router
from trovelya.core.logging import configure_logging
from trovelya.core.middleware import RequestIdMiddleware


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
    app.state.readiness_checks = readiness_checks or {}
    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    return app
