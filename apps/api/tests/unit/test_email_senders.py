"""E-mail adapters (ADR-0017): Resend over HTTPS, SMTP for Mailpit, in-memory for tests."""

import json

import httpx
import pytest

from trovelya.shared.email import (
    EmailDeliveryError,
    EmailMessage,
    FakeEmailSender,
    ResendEmailSender,
)

MESSAGE = EmailMessage(
    to="arcel@example.org", subject="Votre lien", text="Bonjour", html="<p>Bonjour</p>"
)


async def test_resend_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "re_1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = ResendEmailSender(
            api_key="re_key", sender="TROVÉLYA <onboarding@resend.dev>", client=client
        )
        await sender.send(MESSAGE)

    [request] = seen
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_key"
    assert json.loads(request.content) == {
        "from": "TROVÉLYA <onboarding@resend.dev>",
        "to": ["arcel@example.org"],
        "subject": "Votre lien",
        "text": "Bonjour",
        "html": "<p>Bonjour</p>",
    }


@pytest.mark.parametrize("status", [400, 403, 429, 500])
async def test_resend_error_raises_without_address(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "arcel@example.org rejected"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = ResendEmailSender(api_key="k", sender="s@example.org", client=client)
        with pytest.raises(EmailDeliveryError) as error:
            await sender.send(MESSAGE)
    assert "arcel@example.org" not in str(error.value)
    assert str(status) in str(error.value)


async def test_fake_sender_keeps_messages() -> None:
    sender = FakeEmailSender()
    await sender.send(MESSAGE)
    assert sender.sent == [MESSAGE]


def test_message_json_roundtrip() -> None:
    assert EmailMessage.from_json(MESSAGE.to_json()) == MESSAGE
