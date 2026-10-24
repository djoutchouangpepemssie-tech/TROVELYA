"""Routes used only by the test suite. Mounted when ENV is "local" or "test", never elsewhere."""

import asyncio
from itertools import count
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, status

from trovelya.core.idempotency import require_idempotency_key

router = APIRouter(prefix="/v1/_test", tags=["test"], include_in_schema=False)
_executions = count(1)


@router.post(
    "/echo",
    operation_id="test_echo",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_idempotency_key)],
)
async def echo(
    payload: Annotated[dict[str, Any], Body()], delay_ms: int = 0, fail: bool = False
) -> dict[str, Any]:
    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)
    if fail:
        raise RuntimeError("requested failure")
    return {"echo": payload, "execution": next(_executions)}


@router.post(
    "/echo-other",
    operation_id="test_echo_other",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_idempotency_key)],
)
async def echo_other(payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    return {"echo": payload}


@router.get("/ping", operation_id="test_ping")
async def ping() -> dict[str, str]:
    return {"status": "pong"}
