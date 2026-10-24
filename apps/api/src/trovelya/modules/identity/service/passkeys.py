"""Passkeys (WebAuthn), section 13.2 and P1-T04.

- Discoverable credentials with user verification required: a passkey alone is a strong
  sign-in (`mfa_at`), and staff accounts get a 12-hour admin session with it.
- The user handle is `users.id`; only the public key and the signature counter are stored.
- Each challenge is single use and lives 5 minutes: in Redis under its SHA-256 (read with
  `GETDEL`), with its expiry also checked against the application clock.
- Any failure answers `passkey_invalid`, without saying which check failed.
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import structlog
import webauthn
from redis.asyncio import Redis
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes, parse_client_data_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from trovelya.core.config import Settings
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.modules.identity.models import BLOCKED_STATUSES
from trovelya.modules.identity.service.magic_links import SignIn
from trovelya.modules.identity.service.sessions import CurrentUser, SessionPolicy, create_session
from trovelya.shared.clock import Clock
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id

logger = structlog.get_logger(__name__)

CHALLENGE_TTL = timedelta(minutes=5)
_KEY_PREFIX = "webauthn:"
_BLOCKED = {status.value for status in BLOCKED_STATUSES}


@dataclass(frozen=True, slots=True)
class RelyingParty:
    id: str
    name: str
    origins: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: Settings) -> "RelyingParty":
        rp_id = settings.webauthn_rp_id or urlsplit(settings.web_origin).hostname or "localhost"
        origins = settings.webauthn_origins or [settings.web_origin.rstrip("/")]
        return cls(id=rp_id, name=settings.webauthn_rp_name, origins=tuple(origins))


def _invalid() -> AppError:
    return AppError(ErrorCode.PASSKEY_INVALID, 400)


async def _store_challenge(
    redis: Redis, challenge: bytes, *, purpose: str, user_id: UUID | None, now: datetime
) -> None:
    value = {
        "purpose": purpose,
        "user_id": str(user_id) if user_id else None,
        "expires_at": (now + CHALLENGE_TTL).isoformat(),
    }
    key = _KEY_PREFIX + hashlib.sha256(challenge).hexdigest()
    await redis.set(key, json.dumps(value), ex=int(CHALLENGE_TTL.total_seconds()))


async def _take_challenge(
    redis: Redis, credential: dict[str, Any], *, purpose: str, user_id: UUID | None, now: datetime
) -> bytes:
    """The challenge the credential answers, if we issued it for this purpose and user."""
    try:
        client_data = parse_client_data_json(
            base64url_to_bytes(credential["response"]["clientDataJSON"])
        )
    except (KeyError, TypeError, ValueError, WebAuthnException) as exc:
        raise _invalid() from exc
    challenge = client_data.challenge
    raw = await redis.getdel(_KEY_PREFIX + hashlib.sha256(challenge).hexdigest())
    if raw is None:
        raise _invalid()
    stored: dict[str, Any] = json.loads(raw)
    expected_user = str(user_id) if user_id else None
    if (
        stored["purpose"] != purpose
        or stored["user_id"] != expected_user
        or datetime.fromisoformat(stored["expires_at"]) <= now
    ):
        raise _invalid()
    return challenge


async def registration_options(
    db: AsyncSession,
    redis: Redis,
    *,
    user: CurrentUser,
    rp: RelyingParty,
    clock: Clock,
) -> dict[str, Any]:
    existing = await repository.credential_ids(db, user.id)
    user_name = await repository.user_email(db, user.id)
    options = webauthn.generate_registration_options(
        rp_id=rp.id,
        rp_name=rp.name,
        user_id=user.id.bytes,
        user_name=user_name,
        user_display_name=user_name,
        challenge=secrets.token_bytes(32),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in existing],
    )
    await _store_challenge(
        redis, options.challenge, purpose="register", user_id=user.id, now=clock.now()
    )
    return json.loads(webauthn.options_to_json(options))


async def register_passkey(
    db: AsyncSession,
    redis: Redis,
    *,
    user: CurrentUser,
    credential: dict[str, Any],
    name: str,
    rp: RelyingParty,
    clock: Clock,
) -> Row[Any]:
    now = clock.now()
    challenge = await _take_challenge(
        redis, credential, purpose="register", user_id=user.id, now=now
    )
    try:
        verified = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp.id,
            expected_origin=list(rp.origins),
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        logger.info("passkey.registration_rejected", error=type(exc).__name__)
        raise _invalid() from exc
    known = {member.value for member in AuthenticatorTransport}
    declared: Any = credential.get("response", {}).get("transports") or []
    items: list[object] = list(declared) if isinstance(declared, list) else []  # pyright: ignore[reportUnknownArgumentType]
    transports = [str(t) for t in items if t in known]
    row = await repository.insert_passkey(
        db,
        passkey_id=new_id(),
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=transports or None,
        name=name,
        now=now,
    )
    if row is None:
        raise _invalid()
    return row


async def login_options(redis: Redis, *, rp: RelyingParty, clock: Clock) -> dict[str, Any]:
    options = webauthn.generate_authentication_options(
        rp_id=rp.id,
        challenge=secrets.token_bytes(32),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    await _store_challenge(redis, options.challenge, purpose="login", user_id=None, now=clock.now())
    return json.loads(webauthn.options_to_json(options))


async def login_with_passkey(
    db: AsyncSession,
    redis: Redis,
    *,
    credential: dict[str, Any],
    ip: str | None,
    user_agent: str | None,
    country: str | None,
    rp: RelyingParty,
    policy: SessionPolicy,
    clock: Clock,
) -> SignIn:
    now = clock.now()
    challenge = await _take_challenge(redis, credential, purpose="login", user_id=None, now=now)
    try:
        credential_id = base64url_to_bytes(credential["rawId"])
        user_handle = credential["response"].get("userHandle")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _invalid() from exc
    passkey = await repository.find_passkey(db, credential_id)
    if passkey is None or passkey.status in _BLOCKED:
        raise _invalid()
    if user_handle is not None and base64url_to_bytes(user_handle) != passkey.user_id.bytes:
        raise _invalid()
    try:
        verified = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp.id,
            expected_origin=list(rp.origins),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        # Includes a signature counter that went backwards: a possibly cloned authenticator.
        logger.warning("passkey.authentication_rejected", error=type(exc).__name__)
        raise _invalid() from exc
    if not await repository.use_passkey(
        db,
        passkey.id,
        old_count=passkey.sign_count,
        new_count=verified.new_sign_count,
        now=now,
    ):
        raise _invalid()

    issued = await create_session(
        db,
        user_id=passkey.user_id,
        kind="admin" if passkey.is_staff else "web",
        ip=ip,
        user_agent=user_agent,
        country=country,
        strong=True,
        policy=policy,
        clock=clock,
    )
    await emit_event(
        db,
        type="session.created",
        aggregate_type="user",
        aggregate_id=passkey.user_id,
        payload={"session_id": str(issued.session_id)},
    )
    return SignIn(
        user_id=passkey.user_id,
        is_new=False,
        profile_completed=passkey.profile_completed,
        session=issued,
    )


async def list_passkeys(db: AsyncSession, *, user: CurrentUser) -> list[Row[Any]]:
    return await repository.list_passkeys(db, user.id)


async def rename_passkey(
    db: AsyncSession, *, user: CurrentUser, passkey_id: UUID, name: str
) -> Row[Any]:
    row = await repository.rename_passkey(db, passkey_id=passkey_id, user_id=user.id, name=name)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return row


async def delete_passkey(db: AsyncSession, *, user: CurrentUser, passkey_id: UUID) -> None:
    if not await repository.delete_passkey(db, passkey_id=passkey_id, user_id=user.id):
        raise AppError(ErrorCode.NOT_FOUND, 404)
