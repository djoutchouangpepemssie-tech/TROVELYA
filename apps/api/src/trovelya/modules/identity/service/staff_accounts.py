"""Staff accounts: created by script, signed in by passkey only (ADR-0018, Q18, E9).

There is no company e-mail domain yet: a staff account is a separate account (never a customer
account turned staff), created from the server with `python -m trovelya.scripts.create_staff`.
The script prints a single-use enrolment link, valid 15 minutes, which registers the account's
first passkey and opens an admin session. Magic links and Google/Apple stay refused to staff.
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.config import Settings
from trovelya.core.db import commit
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.modules.identity.service import passkeys
from trovelya.modules.identity.service.magic_links import SignIn
from trovelya.modules.identity.service.sessions import SessionPolicy, create_session
from trovelya.shared.audit import record_audit
from trovelya.shared.clock import Clock
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id

ENROLMENT_TTL = timedelta(minutes=15)
_KEY_PREFIX = "enrol:"
_PURPOSE = "enrol"


class StaffAccountError(Exception):
    """The script refuses: message in French, shown in the terminal."""


@dataclass(frozen=True, slots=True)
class StaffEnrolment:
    user_id: UUID
    link: str
    created: bool  # False: a new link for an existing staff account without passkey


def _key(token: str) -> str:
    return _KEY_PREFIX + hashlib.sha256(token.encode()).hexdigest()


async def issue_staff_enrolment(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    email: str,
    role: str,
    settings: Settings,
    clock: Clock,
) -> StaffEnrolment:
    """Creates the staff account (or reuses one that has no passkey yet) and returns its
    enrolment link. Never turns a customer account into a staff one."""
    email = email.strip().lower()
    if not role.startswith("staff_"):
        raise StaffAccountError(f"Le rôle {role!r} n'est pas un rôle staff.")
    now = clock.now()
    async with sessionmaker() as db:
        if not await repository.role_exists(db, role):
            raise StaffAccountError(f"Le rôle {role!r} n'existe pas.")
        existing = await repository.find_user_by_email(db, email)
        if existing is not None and not existing.is_staff:
            raise StaffAccountError(
                "Cette adresse appartient à un compte client : utilisez une adresse distincte"
                " pour le compte staff (par exemple prenom+staff@…)."
            )
        if existing is not None and await repository.credential_ids(db, existing.id):
            raise StaffAccountError(
                "Ce compte staff a déjà une passkey : connectez-vous avec elle."
            )
        user_id: UUID = existing.id if existing is not None else new_id()
        if existing is None:
            await repository.create_staff_user(db, user_id=user_id, email=email, now=now)
            await repository.grant_role(db, user_id=user_id, role=role, granted_by=None)
            await record_audit(
                db,
                actor_type="system",
                actor_id=None,
                action="staff.create",
                target_type="user",
                target_id=str(user_id),
                after={"role": role},
            )
        await record_audit(
            db,
            actor_type="system",
            actor_id=None,
            action="staff.enrolment_link",
            target_type="user",
            target_id=str(user_id),
        )
        await commit(db)
    token = secrets.token_urlsafe(32)
    value = {"user_id": str(user_id), "expires_at": (now + ENROLMENT_TTL).isoformat()}
    await redis.set(_key(token), json.dumps(value), ex=int(ENROLMENT_TTL.total_seconds()))
    link = f"{settings.web_origin.rstrip('/')}/fr/staff/enrolement#token={token}"
    return StaffEnrolment(user_id=user_id, link=link, created=existing is None)


def _invalid() -> AppError:
    return AppError(ErrorCode.ENROLMENT_INVALID, 400)


def _read(raw: Any, *, now: datetime) -> UUID:
    if raw is None:
        raise _invalid()
    stored: dict[str, str] = json.loads(raw)
    if datetime.fromisoformat(stored["expires_at"]) <= now:
        raise _invalid()
    return UUID(stored["user_id"])


async def enrolment_options(
    db: AsyncSession,
    redis: Redis,
    *,
    token: str,
    rp: passkeys.RelyingParty,
    clock: Clock,
) -> dict[str, Any]:
    """Creation options for the account the link was issued for (the link stays valid)."""
    user_id = _read(await redis.get(_key(token)), now=clock.now())
    return await passkeys.registration_options(
        db, redis, user_id=user_id, rp=rp, clock=clock, purpose=_PURPOSE
    )


async def enrol(
    db: AsyncSession,
    redis: Redis,
    *,
    token: str,
    credential: dict[str, Any],
    name: str,
    ip: str | None,
    user_agent: str | None,
    country: str | None,
    rp: passkeys.RelyingParty,
    policy: SessionPolicy,
    clock: Clock,
) -> SignIn:
    """Registers the first passkey and opens an admin session. The link is spent only once the
    passkey is proven, so a refused attempt (wrong site, cancelled) leaves it usable."""
    now = clock.now()
    user_id = _read(await redis.get(_key(token)), now=now)
    verified = await passkeys.verify_registration(
        redis, user_id=user_id, credential=credential, rp=rp, clock=clock, purpose=_PURPOSE
    )
    if _read(await redis.getdel(_key(token)), now=now) != user_id:
        raise _invalid()
    await passkeys.store_passkey(
        db, user_id=user_id, verified=verified, credential=credential, name=name, clock=clock
    )
    issued = await create_session(
        db,
        user_id=user_id,
        kind="admin",
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
        aggregate_id=user_id,
        payload={"session_id": str(issued.session_id)},
    )
    await record_audit(
        db,
        actor_type="staff",
        actor_id=user_id,
        action="staff.passkey_enrolled",
        target_type="user",
        target_id=str(user_id),
        ip=ip,
        user_agent=user_agent,
    )
    return SignIn(user_id=user_id, is_new=False, profile_completed=True, session=issued)
