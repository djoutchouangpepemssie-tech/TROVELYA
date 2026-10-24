"""Cloudflare Turnstile verification (section 13.1), off while TURNSTILE_SECRET_KEY is unset."""

from urllib.parse import parse_qs

import httpx
import pytest

from trovelya.modules.identity.adapters.turnstile import (
    SITEVERIFY_URL,
    AlwaysPass,
    TurnstileVerifier,
)


def _verifier(answer: httpx.Response | Exception, seen: list[httpx.Request]) -> TurnstileVerifier:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return TurnstileVerifier(
        secret="ts", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def test_valid_token_passes_and_sends_secret_token_and_ip() -> None:
    seen: list[httpx.Request] = []
    verifier = _verifier(httpx.Response(200, json={"success": True}), seen)
    assert await verifier.verify("tok", ip="203.0.113.7") is True
    [request] = seen
    assert str(request.url) == SITEVERIFY_URL
    assert parse_qs(request.content.decode()) == {
        "secret": ["ts"],
        "response": ["tok"],
        "remoteip": ["203.0.113.7"],
    }


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, json={"success": False}),
        httpx.Response(500, text="oops"),
        httpx.ConnectError("down"),
    ],
)
async def test_rejected_or_unreachable_fails_closed(answer: httpx.Response | Exception) -> None:
    assert await _verifier(answer, []).verify("tok", ip="203.0.113.7") is False


async def test_missing_token_fails_without_calling_cloudflare() -> None:
    seen: list[httpx.Request] = []
    assert (
        await _verifier(httpx.Response(200, json={"success": True}), seen).verify(
            None, ip="1.2.3.4"
        )
        is False
    )
    assert seen == []


async def test_always_pass_when_disabled() -> None:
    assert await AlwaysPass().verify(None, ip="1.2.3.4") is True
