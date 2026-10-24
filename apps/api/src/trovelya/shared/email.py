"""Transactional e-mail adapters (ADR-0017).

- `ResendEmailSender`: Resend's HTTPS API (staging, while TROVÉLYA has no domain).
- `SmtpEmailSender`: plain SMTP, for Mailpit in local development and CI.
- `FakeEmailSender`: keeps messages in memory, for tests.

Errors never quote the provider's answer, which may contain the recipient's address.
"""

import json
from dataclasses import asdict, dataclass, field
from email.message import EmailMessage as MimeMessage
from typing import Protocol
from urllib.parse import urlsplit

import aiosmtplib
import httpx

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_S = 10.0


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None

    def to_json(self) -> bytes:
        return json.dumps(asdict(self), ensure_ascii=False).encode()

    @classmethod
    def from_json(cls, data: bytes) -> "EmailMessage":
        return cls(**json.loads(data))


class EmailDeliveryError(Exception):
    """The provider refused or could not be reached; the job may be retried."""


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ResendEmailSender:
    def __init__(self, *, api_key: str, sender: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._sender = sender
        self._client = client

    async def send(self, message: EmailMessage) -> None:
        payload: dict[str, object] = {
            "from": self._sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html is not None:
            payload["html"] = message.html
        try:
            response = await self._client.post(
                RESEND_URL,
                json=payload,
                headers={"authorization": f"Bearer {self._api_key}"},
                timeout=TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(f"resend unreachable: {type(exc).__name__}") from None
        if response.status_code >= 300:
            raise EmailDeliveryError(f"resend answered {response.status_code}")


class SmtpEmailSender:
    def __init__(self, *, url: str, sender: str) -> None:
        parts = urlsplit(url)
        self._host = parts.hostname or "localhost"
        self._port = parts.port or 25
        self._sender = sender

    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        if message.html is not None:
            mime.add_alternative(message.html, subtype="html")
        try:
            await aiosmtplib.send(mime, hostname=self._host, port=self._port, timeout=TIMEOUT_S)
        except aiosmtplib.SMTPException as exc:
            raise EmailDeliveryError(f"smtp failed: {type(exc).__name__}") from None


@dataclass
class FakeEmailSender:
    sent: list[EmailMessage] = field(default_factory=list[EmailMessage])

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
