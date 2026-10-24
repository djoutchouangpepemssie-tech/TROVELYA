"""Changing the account's e-mail address (section 13.2, P1-T05c).

- The request needs a recent strong sign-in (step-up). It answers 202 in every case; an
  address already used by an account (this one included) gets no e-mail, so the answer says
  nothing about other accounts.
- The link goes to the new address. Its token is `<account id>.<random>`: only the SHA-256 of
  the whole token is stored, so the account cannot be swapped, and the link works without a
  session (it may be opened on another device).
- On use: the address changes and is marked verified, `user.email_changed` is emitted, and
  the previous address is told, without the new address and without an undo link.
"""

import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.email import JobQueue, enqueue_email
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.modules.identity.emails import email_change_message, email_changed_notice
from trovelya.modules.identity.service.alerts import security_link
from trovelya.modules.identity.service.magic_links import DEFAULT_TTL_MIN, TOKEN_BYTES
from trovelya.modules.identity.service.sessions import CurrentUser, hash_token
from trovelya.shared.clock import Clock
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id

PURPOSE = "change_email"


async def request_email_change(
    db: AsyncSession,
    queue: JobQueue,
    *,
    user: CurrentUser,
    new_email: str,
    ip: str,
    settings: Settings,
    clock: Clock,
) -> None:
    if await repository.email_in_use(db, new_email):
        return
    now = clock.now()
    ttl_min = await repository.setting_int(db, "auth.magic_link_ttl_min", default=DEFAULT_TTL_MIN)
    token = f"{user.id.hex}.{secrets.token_urlsafe(TOKEN_BYTES)}"
    await repository.insert_magic_link(
        db,
        link_id=new_id(),
        email=new_email,
        token_hash=hash_token(token),
        purpose=PURPOSE,
        expires_at=now + timedelta(minutes=ttl_min),
        ip=ip if ip != "unknown" else None,
        now=now,
    )
    link = f"{settings.web_origin.rstrip('/')}/fr/compte/email/confirmer#token={token}"
    message = email_change_message(to=new_email, link=link, ttl_minutes=ttl_min)
    await enqueue_email(db, queue, message, settings=settings)


def _account_of(token: str) -> UUID:
    prefix, _, secret = token.partition(".")
    try:
        user_id = UUID(hex=prefix)
    except ValueError as exc:
        raise AppError(ErrorCode.MAGIC_LINK_INVALID, 400) from exc
    if not secret:
        raise AppError(ErrorCode.MAGIC_LINK_INVALID, 400)
    return user_id


async def verify_email_change(
    db: AsyncSession,
    queue: JobQueue,
    token: str,
    *,
    settings: Settings,
    clock: Clock,
) -> None:
    user_id = _account_of(token)
    now = clock.now()
    new_email = await repository.consume_magic_link(
        db, token_hash=hash_token(token), purpose=PURPOSE, now=now
    )
    if new_email is None:
        raise AppError(ErrorCode.MAGIC_LINK_INVALID, 400)
    old_email = await repository.user_email(db, user_id)
    try:
        async with db.begin_nested():
            changed = await repository.change_email(db, user_id=user_id, email=new_email, now=now)
    except IntegrityError as exc:
        raise AppError(ErrorCode.EMAIL_TAKEN, 409) from exc
    if not changed:
        raise AppError(ErrorCode.MAGIC_LINK_INVALID, 400)
    await emit_event(
        db, type="user.email_changed", aggregate_type="user", aggregate_id=user_id, payload={}
    )
    notice = email_changed_notice(to=old_email, security_link=security_link(settings))
    await enqueue_email(db, queue, notice, settings=settings)
