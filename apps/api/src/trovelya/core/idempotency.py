"""HTTP idempotency keys (section 11.1, ADR-0012).

For unsafe methods carrying `Idempotency-Key` (a UUID): the first request runs and its
response is stored; a retry with the same key and the same request gets the stored response
(`Idempotent-Replayed: true`); the same key with another request gets 409
`idempotency_conflict`; a retry while the first is still running gets 409
`idempotency_in_progress`. A 5xx or a crash releases the key so the client can retry.
Keys are kept 72 hours. Routes that require a key declare `require_idempotency_key`.
"""

import hashlib
import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import structlog
from fastapi import Header
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from trovelya.core.errors import AppError, ErrorCode, problem_response
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

HEADER = "idempotency-key"
REPLAYED_HEADER = "idempotent-replayed"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
KEY_TTL = timedelta(hours=72)

_CLAIM = text(
    "INSERT INTO idempotency_keys (key, user_id, method, path, request_hash)"
    " VALUES (:key, :user_id, :method, :path, :hash)"
    " ON CONFLICT ON CONSTRAINT idempotency_keys_key_user_uniq DO NOTHING RETURNING id"
)
_FIND = text(
    "SELECT method, path, request_hash, response_status, response_body FROM idempotency_keys"
    " WHERE key = :key AND user_id IS NOT DISTINCT FROM :user_id"
)
_STORE = text(
    "UPDATE idempotency_keys SET response_status = :status, response_body = :body WHERE id = :id"
).bindparams(bindparam("body", type_=JSONB))
_RELEASE = text("DELETE FROM idempotency_keys WHERE id = :id")


def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    """Dependency for routes where the key is mandatory (checkout, offers, payouts…)."""
    if idempotency_key is None:
        raise AppError(ErrorCode.IDEMPOTENCY_KEY_REQUIRED, 400)
    return idempotency_key


def _request_hash(method: str, path: str, body: bytes) -> str:
    try:
        canonical = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")).encode()
    except ValueError:
        canonical = body
    return hashlib.sha256(method.encode() + b"\n" + path.encode() + b"\n" + canonical).hexdigest()


def _header(scope: Scope, name: str) -> str | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1") == name:
            return value.decode("latin-1")
    return None


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        raw_key = _header(scope, HEADER)
        if raw_key is None:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        try:
            key = str(UUID(raw_key))
        except ValueError:
            await problem_response(request, ErrorCode.IDEMPOTENCY_KEY_INVALID, 400)(
                scope, receive, send
            )
            return

        body = await _read_body(receive)
        method, path = scope["method"], scope["path"]
        user_id: UUID | None = scope.get("state", {}).get("user_id")
        request_hash = _request_hash(method, path, body)
        sessionmaker: async_sessionmaker[AsyncSession] = scope["app"].state.sessionmaker

        async with sessionmaker() as session, session.begin():
            row_id = await session.scalar(
                _CLAIM,
                {
                    "key": key,
                    "user_id": user_id,
                    "method": method,
                    "path": path,
                    "hash": request_hash,
                },
            )
            existing = (
                None
                if row_id is not None
                else (await session.execute(_FIND, {"key": key, "user_id": user_id})).one_or_none()
            )

        if row_id is None:
            await self._answer_existing(request, existing, request_hash, scope, receive, send)
            return
        await self._run_and_store(scope, body, send, sessionmaker, row_id)

    async def _answer_existing(
        self,
        request: Request,
        existing: Any,
        request_hash: str,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if existing is None or existing.request_hash != request_hash:
            response: Response = problem_response(request, ErrorCode.IDEMPOTENCY_CONFLICT, 409)
        elif existing.response_status is None:
            response = problem_response(request, ErrorCode.IDEMPOTENCY_IN_PROGRESS, 409)
        else:
            stored: dict[str, str] = existing.response_body
            response = Response(
                content=stored["text"],
                status_code=existing.response_status,
                media_type=stored["content_type"],
                headers={REPLAYED_HEADER: "true"},
            )
        await response(scope, receive, send)

    async def _run_and_store(
        self,
        scope: Scope,
        body: bytes,
        send: Send,
        sessionmaker: async_sessionmaker[AsyncSession],
        row_id: int,
    ) -> None:
        sent = False

        async def replay_body() -> Message:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        status = 500
        content_type = "application/json"
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal status, content_type
            if message["type"] == "http.response.start":
                status = message["status"]
                for name, value in message.get("headers", []):
                    if name.lower() == b"content-type":
                        content_type = value.decode("latin-1")
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, replay_body, capture)
        except BaseException:
            await _finish(sessionmaker, row_id, None)
            raise
        stored = (
            None
            if status >= 500
            else {"content_type": content_type, "text": b"".join(chunks).decode("utf-8", "replace")}
        )
        await _finish(sessionmaker, row_id, None if stored is None else (status, stored))


async def _finish(
    sessionmaker: async_sessionmaker[AsyncSession],
    row_id: int,
    result: tuple[int, dict[str, str]] | None,
) -> None:
    async with sessionmaker() as session, session.begin():
        if result is None:
            await session.execute(_RELEASE, {"id": row_id})
        else:
            await session.execute(_STORE, {"id": row_id, "status": result[0], "body": result[1]})


async def purge_idempotency_keys(
    sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock, ttl: timedelta = KEY_TTL
) -> int:
    """Delete keys older than `ttl` (72 hours by default). Returns the number deleted."""
    async with sessionmaker() as session, session.begin():
        result = await session.execute(
            text("DELETE FROM idempotency_keys WHERE created_at < :cutoff"),
            {"cutoff": clock.now() - ttl},
        )
    return int(result.rowcount)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownArgumentType, reportUnknownMemberType]
