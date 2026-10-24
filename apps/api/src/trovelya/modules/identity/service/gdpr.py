"""Self-service GDPR rights (articles 15, 17 and 20, section 14.1).

Export (ADR-0016): the request is answered at once (202); the worker builds a ZIP
(`export.json`, one key per registered exporter, and `LISEZMOI.txt`), seals it with a key used
for nothing else and keeps it 7 days.

Erasure (Q10): the request signs the person out everywhere and hides the public profile; after
a grace period (30 days, `retention.erasure_grace_days`) during which signing in again allows
to cancel, a daily job runs every module's eraser and anonymises the account.

Requesting an export or an erasure needs a recent strong sign-in; every step is audited.
"""

import io
import json
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.config import Settings
from trovelya.core.db import commit, on_commit
from trovelya.core.email import JobQueue, enqueue_email
from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.gdpr import (
    register_eraser,
    register_exporter,
    registered_erasers,
    registered_exporters,
)
from trovelya.modules.identity import repository
from trovelya.modules.identity.emails import erasure_requested_message, export_ready_message
from trovelya.shared.audit import record_audit
from trovelya.shared.clock import Clock
from trovelya.shared.crypto import derive_key, open_sealed, seal
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id

logger = structlog.get_logger(__name__)

EXPORT_JOB = "build_data_export"
DEFAULT_EXPORT_DAYS = 7
_PURPOSE = "gdpr-export"
_README = """Export de vos données TROVÉLYA

export.json contient toutes les données personnelles que TROVÉLYA détient sur vous, rangées
par module (« identity » : votre compte, vos connexions, adresses, zones, préférences,
consentements, abonnements, blocages et demandes).

Ne figurent pas dans cet export : les secrets de sécurité (empreintes de jetons de connexion,
clés de vos passkeys) et les données d'autres personnes (qui vous bloque ; vos abonnés sont
comptés, pas nommés).

Pour toute question : la politique de confidentialité, sur le site.
"""


async def export_identity(db: AsyncSession, user_id: UUID) -> dict[str, Any]:
    data: dict[str, Any] = {
        name: await repository.export_rows(db, query, user_id)
        for name, query in repository.EXPORT_QUERIES.items()
    }
    data["follows"] = await repository.export_follows(db, user_id)
    return data


register_exporter("identity", export_identity)
register_eraser("identity", repository.erase_identity)


def _json_default(value: object) -> str | float:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"not serialisable: {type(value).__name__}")


def _key(settings: Settings) -> bytes:
    return derive_key(settings.field_encryption_key.get_secret_value(), purpose=_PURPOSE)


def _aad(request_id: UUID) -> bytes:
    # Bound to its request: an archive copied onto another request does not open.
    return f"trovelya:gdpr-export:v1:{request_id}".encode()


def account_data_link(settings: Settings) -> str:
    return f"{settings.web_origin.rstrip('/')}/fr/compte/donnees"


async def request_export(
    db: AsyncSession,
    *,
    user_id: UUID,
    queue: JobQueue,
    clock: Clock,
    ip: str | None,
    user_agent: str | None,
) -> UUID:
    """The pending request if there is one (review point 5), else a new one and its job."""
    existing = await repository.pending_data_request(db, user_id, "export")
    if existing is not None:
        return existing
    request_id = new_id()
    try:
        async with db.begin_nested():
            await repository.insert_data_request(
                db, request_id=request_id, user_id=user_id, kind="export", now=clock.now()
            )
    except IntegrityError:  # a concurrent request won the unique index
        existing = await repository.pending_data_request(db, user_id, "export")
        if existing is None:
            raise
        return existing
    await record_audit(
        db,
        actor_type="user",
        actor_id=user_id,
        action="gdpr.export_requested",
        target_type="data_request",
        target_id=str(request_id),
        ip=ip,
        user_agent=user_agent,
    )

    async def push() -> None:
        await queue.enqueue_job(EXPORT_JOB, str(request_id))

    on_commit(db, push)
    return request_id


async def build_data_export(
    sessionmaker: async_sessionmaker[AsyncSession],
    request_id: UUID,
    *,
    settings: Settings,
    clock: Clock,
    queue: JobQueue,
) -> bool:
    """Worker job. False when there is nothing to do (unknown or already handled request)."""
    async with sessionmaker() as db:
        request = await repository.export_request_for_build(db, request_id)
        if request is None or request.status not in ("received", "processing"):
            return False
        data = {name: await fn(db, request.user_id) for name, fn in registered_exporters().items()}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "export.json",
                json.dumps(data, default=_json_default, ensure_ascii=False, indent=2),
            )
            archive.writestr("LISEZMOI.txt", _README)
        now = clock.now()
        days = await repository.setting_int(
            db, "retention.data_export_days", default=DEFAULT_EXPORT_DAYS
        )
        await repository.store_export(
            db,
            request_id=request_id,
            ciphertext=seal(buffer.getvalue(), key=_key(settings), aad=_aad(request_id)),
            expires_at=now + timedelta(days=days),
            now=now,
        )
        await record_audit(
            db,
            actor_type="system",
            actor_id=None,
            action="gdpr.export_built",
            target_type="data_request",
            target_id=str(request_id),
        )
        message = export_ready_message(
            to=request.email, link=account_data_link(settings), days=days
        )
        await enqueue_email(db, queue, message, settings=settings)
        await commit(db)
    logger.info("gdpr.export_built", request_id=str(request_id))
    return True


async def list_requests(db: AsyncSession, user_id: UUID) -> list[Any]:
    return await repository.list_data_requests(db, user_id)


async def download_export(
    db: AsyncSession,
    *,
    user_id: UUID,
    request_id: UUID,
    settings: Settings,
    clock: Clock,
    ip: str | None,
    user_agent: str | None,
) -> bytes:
    """The decrypted ZIP; 404 for someone else's, unknown, unfinished or expired export."""
    sealed = await repository.export_ciphertext(
        db, request_id=request_id, user_id=user_id, now=clock.now()
    )
    if sealed is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    archive = open_sealed(sealed, key=_key(settings), aad=_aad(request_id))
    await record_audit(
        db,
        actor_type="user",
        actor_id=user_id,
        action="gdpr.export_downloaded",
        target_type="data_request",
        target_id=str(request_id),
        ip=ip,
        user_agent=user_agent,
    )
    return archive


async def purge_expired_exports(
    sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock
) -> int:
    async with sessionmaker() as db:
        purged = await repository.purge_expired_exports(db, now=clock.now())
        await commit(db)
    return purged


# --- Erasure ---------------------------------------------------------------------------------

DEFAULT_GRACE_DAYS = 30
ERASURE_BATCH = 100
PARIS = ZoneInfo("Europe/Paris")
_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def french_date(moment: datetime) -> str:
    local = moment.astimezone(PARIS)
    return f"{local.day} {_MONTHS[local.month - 1]} {local.year}"


async def _grace(db: AsyncSession) -> timedelta:
    days = await repository.setting_int(
        db, "retention.erasure_grace_days", default=DEFAULT_GRACE_DAYS
    )
    return timedelta(days=days)


async def request_erasure(
    db: AsyncSession,
    *,
    user_id: UUID,
    queue: JobQueue,
    settings: Settings,
    clock: Clock,
    ip: str | None,
    user_agent: str | None,
) -> datetime:
    """Signs the person out everywhere; answers when the account will be erased. Asking again
    during the grace period keeps the first date."""
    now = clock.now()
    requested_at = await repository.request_erasure(db, user_id=user_id, now=now)
    if requested_at is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    erase_at = requested_at + await _grace(db)
    await repository.revoke_sessions(db, user_id=user_id, except_id=None, now=now)
    if await repository.pending_data_request(db, user_id, "erasure") is not None:
        return erase_at
    await repository.insert_data_request(
        db, request_id=new_id(), user_id=user_id, kind="erasure", now=now
    )
    await record_audit(
        db,
        actor_type="user",
        actor_id=user_id,
        action="user.erasure_requested",
        target_type="user",
        target_id=str(user_id),
        ip=ip,
        user_agent=user_agent,
    )
    message = erasure_requested_message(
        to=await repository.user_email(db, user_id),
        erase_on=french_date(erase_at),
        signin_link=f"{settings.web_origin.rstrip('/')}/fr/connexion",
    )
    await enqueue_email(db, queue, message, settings=settings)
    return erase_at


async def cancel_erasure(
    db: AsyncSession, *, user_id: UUID, clock: Clock, ip: str | None, user_agent: str | None
) -> None:
    if not await repository.cancel_erasure(db, user_id=user_id, now=clock.now()):
        raise AppError(ErrorCode.NO_ERASURE_PENDING, 409)
    await record_audit(
        db,
        actor_type="user",
        actor_id=user_id,
        action="user.erasure_cancelled",
        target_type="user",
        target_id=str(user_id),
        ip=ip,
        user_agent=user_agent,
    )


async def _erase(db: AsyncSession, user_id: UUID, *, now: datetime) -> None:
    # Other modules first, identity last: its eraser still needs the e-mail address.
    erasers = registered_erasers()
    for name, eraser in erasers.items():
        if name != "identity":
            await eraser(db, user_id)
    await erasers["identity"](db, user_id)
    await repository.anonymise_user(db, user_id=user_id, now=now)
    await emit_event(
        db, type="user.deleted", aggregate_type="user", aggregate_id=user_id, payload={}
    )
    await record_audit(
        db,
        actor_type="system",
        actor_id=None,
        action="user.erase",
        target_type="user",
        target_id=str(user_id),
    )


async def process_erasures(sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock) -> int:
    """Daily job: erases every account whose grace period is over, one transaction each."""
    now = clock.now()
    async with sessionmaker() as db:
        cutoff = now - await _grace(db)
        due = await repository.due_erasures(db, cutoff=cutoff, limit=ERASURE_BATCH)
    erased = 0
    for user_id in due:
        async with sessionmaker() as db:
            if not await repository.lock_due_erasure(db, user_id=user_id, cutoff=cutoff):
                continue  # cancelled meanwhile, or another worker has it
            await _erase(db, user_id, now=now)
            await commit(db)
            erased += 1
    if erased:
        logger.info("gdpr.accounts_erased", count=erased)
    return erased
