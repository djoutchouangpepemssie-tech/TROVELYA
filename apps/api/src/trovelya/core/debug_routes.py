"""Deliberate failure to check error tracking end to end. Never mounted in production."""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/_debug", tags=["debug"], include_in_schema=False)


class DebugError(RuntimeError):
    """Raised on purpose by GET /v1/_debug/error."""


@router.get("/error", operation_id="debug_error")
async def debug_error() -> None:
    raise DebugError("Deliberate error to check Sentry (GET /v1/_debug/error)")
