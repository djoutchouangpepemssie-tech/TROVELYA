"""RFC 9457 problem details (docs/CAHIER_DES_CHARGES.md section 11.2)."""

from enum import StrEnum
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"
ERROR_TYPE_BASE = "https://docs.trovelya.com/errors/"

logger = structlog.get_logger(__name__)


class ErrorCode(StrEnum):
    INTERNAL_ERROR = "internal_error"
    VALIDATION_ERROR = "validation_error"
    BAD_REQUEST = "bad_request"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    IDEMPOTENCY_KEY_REQUIRED = "idempotency_key_required"
    IDEMPOTENCY_KEY_INVALID = "idempotency_key_invalid"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    IDEMPOTENCY_IN_PROGRESS = "idempotency_in_progress"
    RATE_LIMITED = "rate_limited"
    CSRF_FAILED = "csrf_failed"
    PRECONDITION_FAILED = "precondition_failed"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    MAGIC_LINK_INVALID = "magic_link_invalid"
    CAPTCHA_FAILED = "captcha_failed"
    OAUTH_FAILED = "oauth_failed"
    OAUTH_EMAIL_UNVERIFIED = "oauth_email_unverified"
    PASSKEY_INVALID = "passkey_invalid"
    STEP_UP_REQUIRED = "step_up_required"
    TOO_YOUNG = "too_young"
    USERNAME_TAKEN = "username_taken"
    PROFILE_INCOMPLETE = "profile_incomplete"
    PROFILE_ALREADY_COMPLETED = "profile_already_completed"


# French titles by default (section 2); translation by Accept-Language arrives with P1.
_TITLES: dict[ErrorCode, str] = {
    ErrorCode.INTERNAL_ERROR: "Erreur interne",
    ErrorCode.VALIDATION_ERROR: "Requête invalide",
    ErrorCode.BAD_REQUEST: "Requête mal formée",
    ErrorCode.NOT_FOUND: "Introuvable",
    ErrorCode.METHOD_NOT_ALLOWED: "Méthode non autorisée",
    ErrorCode.IDEMPOTENCY_KEY_REQUIRED: "Clé d'idempotence obligatoire",
    ErrorCode.IDEMPOTENCY_KEY_INVALID: "Clé d'idempotence invalide",
    ErrorCode.IDEMPOTENCY_CONFLICT: "Clé d'idempotence déjà utilisée",
    ErrorCode.IDEMPOTENCY_IN_PROGRESS: "Requête déjà en cours",
    ErrorCode.RATE_LIMITED: "Trop de requêtes",
    ErrorCode.CSRF_FAILED: "Jeton CSRF invalide",
    ErrorCode.PRECONDITION_FAILED: "Version obsolète",
    ErrorCode.SERVICE_UNAVAILABLE: "Service indisponible",
    ErrorCode.UNAUTHENTICATED: "Connexion requise",
    ErrorCode.FORBIDDEN: "Action non autorisée",
    ErrorCode.MAGIC_LINK_INVALID: "Lien de connexion invalide ou expiré",
    ErrorCode.CAPTCHA_FAILED: "Vérification anti-robots échouée",
    ErrorCode.OAUTH_FAILED: "Connexion avec ce compte impossible",
    ErrorCode.OAUTH_EMAIL_UNVERIFIED: "Adresse e-mail non vérifiée chez le fournisseur",
    ErrorCode.PASSKEY_INVALID: "Clé d'accès refusée",
    ErrorCode.STEP_UP_REQUIRED: "Confirmez votre identité pour continuer",
    ErrorCode.TOO_YOUNG: "Âge minimal non atteint",
    ErrorCode.USERNAME_TAKEN: "Pseudo déjà utilisé",
    ErrorCode.PROFILE_INCOMPLETE: "Profil à compléter",
    ErrorCode.PROFILE_ALREADY_COMPLETED: "Profil déjà complété",
}

_STATUS_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    412: ErrorCode.PRECONDITION_FAILED,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class AppError(Exception):
    """Expected error, rendered as problem details. Never carries internal details."""

    def __init__(
        self,
        code: ErrorCode,
        status: int,
        detail: str | None = None,
        errors: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.status = status
        self.detail = detail
        self.errors = errors
        self.headers = headers


def problem_response(
    request: Request,
    code: ErrorCode,
    status: int,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": ERROR_TYPE_BASE + code.value,
        "title": _TITLES[code],
        "status": status,
        "code": code.value,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", None),
    }
    if detail is not None:
        body["detail"] = detail
    if errors:
        body["errors"] = [e.model_dump() for e in errors]
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(AppError, exc)
    return problem_response(request, exc.code, exc.status, exc.detail, exc.errors, exc.headers)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    code = _STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return problem_response(
        request, code, exc.status_code, headers=dict(exc.headers) if exc.headers else None
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    errors = [
        FieldError(
            # Drop the location prefix ("body", "query"…) to expose the field path only.
            field=".".join(str(part) for part in err["loc"][1:]) or str(err["loc"][0]),
            code=str(err["type"]),
            message=str(err["msg"]),
        )
        for err in exc.errors()
    ]
    return problem_response(request, ErrorCode.VALIDATION_ERROR, 422, errors=errors)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", exc_info=exc)
    return problem_response(request, ErrorCode.INTERNAL_ERROR, 500)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
