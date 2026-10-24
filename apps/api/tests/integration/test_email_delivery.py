"""E-mail delivery through the worker (P1-T02c, part 1).

An e-mail is queued only when the transaction that asked for it commits; the job payload is
sealed (no address or link in clear in Redis); the worker opens it and sends it, with retries.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from arq import Retry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.core.container import DockerContainer

from tests.conftest import make_settings
from trovelya.core.db import commit
from trovelya.core.email import EMAIL_JOB, enqueue_email, open_email, seal_email
from trovelya.shared.email import (
    EmailDeliveryError,
    EmailMessage,
    FakeEmailSender,
    SmtpEmailSender,
)
from trovelya.workers.email_jobs import MAX_TRIES, deliver_email

MESSAGE = EmailMessage(to="arcel@example.org", subject="Votre lien", text="https://x/#token=t")


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


async def test_enqueue_only_after_commit(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    settings, queue = make_settings(), RecordingQueue()
    async with sessionmaker() as db:
        await enqueue_email(db, queue, MESSAGE, settings=settings)
        await db.rollback()
    assert queue.jobs == []

    async with sessionmaker() as db:
        await enqueue_email(db, queue, MESSAGE, settings=settings)
        assert queue.jobs == []
        await commit(db)
    [(function, (sealed,))] = queue.jobs
    assert function == EMAIL_JOB
    assert b"arcel@example.org" not in sealed and b"token" not in sealed
    assert open_email(sealed, settings=settings) == MESSAGE


async def test_deliver_email_job_sends() -> None:
    settings, sender = make_settings(), FakeEmailSender()
    ctx = {"settings": settings, "email_sender": sender, "job_try": 1}
    await deliver_email(ctx, seal_email(MESSAGE, settings=settings))
    assert sender.sent == [MESSAGE]


class FailingSender:
    async def send(self, message: EmailMessage) -> None:
        raise EmailDeliveryError("resend answered 500")


async def test_deliver_email_retries_then_gives_up() -> None:
    settings = make_settings()
    sealed = seal_email(MESSAGE, settings=settings)
    ctx: dict[str, Any] = {"settings": settings, "email_sender": FailingSender(), "job_try": 1}
    with pytest.raises(Retry):
        await deliver_email(ctx, sealed)
    ctx["job_try"] = MAX_TRIES
    with pytest.raises(EmailDeliveryError):
        await deliver_email(ctx, sealed)


async def test_sealed_with_another_key_is_rejected() -> None:
    sealed = seal_email(MESSAGE, settings=make_settings(field_encryption_key="k" * 64))
    ctx = {"settings": make_settings(), "email_sender": FakeEmailSender(), "job_try": 1}
    with pytest.raises(ValueError, match="sealed"):
        await deliver_email(ctx, sealed)


@pytest.fixture(scope="module")
def mailpit() -> Iterator[tuple[str, str]]:
    container = DockerContainer("axllent/mailpit:v1.32.0").with_exposed_ports(1025, 8025)
    with container:
        host = container.get_container_host_ip()
        smtp = f"smtp://{host}:{container.get_exposed_port(1025)}"
        api = f"http://{host}:{container.get_exposed_port(8025)}"
        yield smtp, api


async def test_smtp_sender_reaches_mailpit(mailpit: tuple[str, str]) -> None:
    smtp_url, api = mailpit
    async with httpx.AsyncClient(base_url=api) as client:
        for _ in range(50):  # Mailpit needs a moment before accepting connections
            try:
                await client.get("/api/v1/messages")
                break
            except httpx.TransportError:
                await asyncio.sleep(0.2)
        await SmtpEmailSender(url=smtp_url, sender="TROVÉLYA <no-reply@localhost>").send(
            EmailMessage(
                to="arcel@example.org", subject="Bienvenue", text="Bonjour", html="<p>Bonjour</p>"
            )
        )
        messages = (await client.get("/api/v1/messages")).json()
    assert messages["total"] == 1
    assert messages["messages"][0]["Subject"] == "Bienvenue"
