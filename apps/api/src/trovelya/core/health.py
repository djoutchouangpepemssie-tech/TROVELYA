"""Liveness (/health) and readiness (/ready: database and Redis reachable)."""

from collections.abc import Awaitable, Callable, Mapping

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from trovelya.core.errors import ErrorCode, problem_response

ReadinessCheck = Callable[[], Awaitable[None]]

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", operation_id="health_get")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", operation_id="ready_get", response_model=None)
async def ready(request: Request) -> JSONResponse | dict[str, object]:
    checks: Mapping[str, ReadinessCheck] = request.app.state.readiness_checks
    results: dict[str, str] = {}
    for name, check in checks.items():
        try:
            await check()
            results[name] = "ok"
        except Exception as exc:  # noqa: BLE001 — any failure means "not ready"
            logger.warning("readiness_check_failed", check=name, error=type(exc).__name__)
            results[name] = "unavailable"
    if all(state == "ok" for state in results.values()):
        return {"status": "ok", "checks": results}
    return problem_response(request, ErrorCode.SERVICE_UNAVAILABLE, 503)
