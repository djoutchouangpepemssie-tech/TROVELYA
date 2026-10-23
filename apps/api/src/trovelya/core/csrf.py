"""CSRF protection for cookie-authenticated requests: signed double-submit cookie (11.1).

`GET /v1/csrf` sets `trv_csrf` = `<random>.<HMAC(SECRET_KEY, random)>` (readable by the page).
Any unsafe request that carries the session cookie must echo it in `X-CSRF-Token`.
Requests without the session cookie (mobile bearer tokens, anonymous) are not concerned.
"""

import hashlib
import hmac
import secrets

from fastapi import APIRouter, Request, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from trovelya.core.errors import ErrorCode, problem_response

CSRF_COOKIE = "trv_csrf"
CSRF_HEADER = "x-csrf-token"
SESSION_COOKIE = "trv_session"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _sign(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def issue_csrf_token(secret: str) -> str:
    value = secrets.token_urlsafe(32)
    return f"{value}.{_sign(secret, value)}"


def is_valid_csrf_token(secret: str, token: str) -> bool:
    value, _, signature = token.partition(".")
    return bool(value) and hmac.compare_digest(signature, _sign(secret, value))


class CsrfMiddleware:
    def __init__(self, app: ASGIApp, *, secret: str) -> None:
        self.app = app
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        if SESSION_COOKIE not in request.cookies:
            await self.app(scope, receive, send)
            return
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get(CSRF_HEADER, "")
        if (
            cookie
            and hmac.compare_digest(cookie, header)
            and is_valid_csrf_token(self.secret, cookie)
        ):
            await self.app(scope, receive, send)
            return
        await problem_response(request, ErrorCode.CSRF_FAILED, 403)(scope, receive, send)


router = APIRouter(tags=["security"])


@router.get("/v1/csrf", operation_id="csrf_get")
async def csrf_token(request: Request, response: Response) -> dict[str, str]:
    token = issue_csrf_token(request.app.state.settings.secret_key.get_secret_value())
    response.set_cookie(CSRF_COOKIE, token, secure=True, httponly=False, samesite="lax", path="/")
    return {"csrf_token": token}
