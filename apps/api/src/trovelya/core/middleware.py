"""Request identifier propagated in responses, logs and problem details (section 11.1)."""

import re

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from trovelya.shared.ids import new_id

REQUEST_ID_HEADER = "x-request-id"
# A client-supplied identifier is reused only if it is short and safe to log.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.decode("latin-1") == REQUEST_ID_HEADER:
            candidate = value.decode("latin-1")
            return candidate if _SAFE_REQUEST_ID.match(candidate) else None
    return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or f"req_{new_id().hex}"
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            await self.app(scope, receive, send_with_header)
