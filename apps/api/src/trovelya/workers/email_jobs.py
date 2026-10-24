"""Worker job that sends one queued e-mail (core/email.py), retried with growing delays."""

from typing import Any

import structlog
from arq import Retry

from trovelya.core.email import open_email
from trovelya.shared.email import EmailDeliveryError, EmailSender

logger = structlog.get_logger(__name__)

MAX_TRIES = 5


async def deliver_email(ctx: dict[str, Any], sealed: bytes) -> None:
    message = open_email(sealed, settings=ctx["settings"])
    sender: EmailSender = ctx["email_sender"]
    attempt: int = ctx["job_try"]
    try:
        await sender.send(message)
    except EmailDeliveryError as exc:
        if attempt >= MAX_TRIES:
            # Logged without the address; Sentry gets the error, the person can ask again.
            logger.error("email.delivery_abandoned", error=str(exc), attempts=attempt)
            raise
        logger.warning("email.delivery_retry", error=str(exc), attempt=attempt)
        raise Retry(defer=2**attempt) from exc
    logger.info("email.delivered", attempt=attempt)
