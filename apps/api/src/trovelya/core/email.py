"""Queueing transactional e-mails (ADR-0017).

`enqueue_email` hands a message to the worker only once the caller's transaction commits, so a
rolled-back sign-up never sends a link. The job payload is sealed (AES-256-GCM): Redis never
holds an address or a sign-in link in clear (docs/data/PII.md).
"""

from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.db import on_commit
from trovelya.shared.crypto import SealError, derive_key, open_sealed, seal
from trovelya.shared.email import (
    EmailMessage,
    EmailSender,
    FakeEmailSender,
    ResendEmailSender,
    SmtpEmailSender,
)

EMAIL_JOB = "deliver_email"
_PURPOSE = "email-job"
_AAD = b"trovelya:email-job:v1"


class JobQueue(Protocol):
    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> Any: ...


def _key(settings: Settings) -> bytes:
    return derive_key(settings.field_encryption_key.get_secret_value(), purpose=_PURPOSE)


def seal_email(message: EmailMessage, *, settings: Settings) -> bytes:
    return seal(message.to_json(), key=_key(settings), aad=_AAD)


def open_email(blob: bytes, *, settings: Settings) -> EmailMessage:
    try:
        return EmailMessage.from_json(open_sealed(blob, key=_key(settings), aad=_AAD))
    except SealError as exc:
        raise ValueError("sealed e-mail job rejected (wrong FIELD_ENCRYPTION_KEY?)") from exc


async def enqueue_email(
    db: AsyncSession, queue: JobQueue, message: EmailMessage, *, settings: Settings
) -> None:
    sealed = seal_email(message, settings=settings)

    async def push() -> None:
        await queue.enqueue_job(EMAIL_JOB, sealed)

    on_commit(db, push)


def make_email_sender(settings: Settings, client: httpx.AsyncClient) -> EmailSender:
    if settings.email_provider == "resend" and settings.email_api_key is not None:
        return ResendEmailSender(
            api_key=settings.email_api_key.get_secret_value(),
            sender=settings.email_from,
            client=client,
        )
    if settings.email_provider == "smtp":
        return SmtpEmailSender(url=settings.smtp_url, sender=settings.email_from)
    return FakeEmailSender()
