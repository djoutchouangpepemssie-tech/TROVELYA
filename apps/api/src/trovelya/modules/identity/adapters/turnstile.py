"""Anti-bot check on sign-in requests (section 13.1, decision Q7).

Cloudflare Turnstile, on the basis of legitimate interest (security). Without
`TURNSTILE_SECRET_KEY` the check is off (`AlwaysPass`).
"""

from typing import Protocol

import httpx

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class CaptchaVerifier(Protocol):
    async def verify(self, token: str | None, *, ip: str) -> bool: ...


class AlwaysPass:
    async def verify(self, token: str | None, *, ip: str) -> bool:
        return True


class TurnstileVerifier:
    def __init__(self, *, secret: str, client: httpx.AsyncClient) -> None:
        self._secret = secret
        self._client = client

    async def verify(self, token: str | None, *, ip: str) -> bool:
        if not token:
            return False
        try:
            response = await self._client.post(
                SITEVERIFY_URL,
                data={"secret": self._secret, "response": token, "remoteip": ip},
                timeout=5.0,
            )
            return bool(response.json().get("success"))
        except (httpx.HTTPError, ValueError):
            return False
