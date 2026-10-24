"""OpenID Connect sign-in (Google; Apple later), authorization code flow with PKCE (13.2).

The ID token comes straight from the provider's token endpoint over TLS, and is still fully
checked: RS256 signature against the provider's published keys (cached 1 hour), issuer,
audience, expiry and the nonce bound to the browser's sign-in attempt.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

ALGORITHM = "RS256"
CLOCK_SKEW = timedelta(seconds=60)
JWKS_TTL = timedelta(hours=1)
PKCE_VERIFIER_BYTES = 48  # 64 characters, within RFC 7636's 43 to 128


class OidcError(Exception):
    """The provider refused the code or returned a token that fails validation."""


@dataclass(frozen=True, slots=True)
class OidcConfig:
    name: str
    issuers: tuple[str, ...]
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str = "openid email profile"


def google_config(*, client_id: str, client_secret: str, redirect_uri: str) -> OidcConfig:
    return OidcConfig(
        name="google",
        # Google documents both spellings of its issuer.
        issuers=("https://accounts.google.com", "accounts.google.com"),
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",  # noqa: S106 — a URL
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )


@dataclass(frozen=True, slots=True)
class IdTokenClaims:
    sub: str
    email: str | None
    email_verified: bool
    is_private_email: bool  # Apple "Hide my e-mail" relay address


def new_pkce() -> tuple[str, str]:
    """(code_verifier, S256 code_challenge)."""
    verifier = secrets.token_urlsafe(PKCE_VERIFIER_BYTES)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _flag(value: Any) -> bool:
    # Google sends booleans, Apple sends the strings "true" and "false".
    return value is True or value == "true"


class OidcProvider:
    def __init__(self, config: OidcConfig, client: httpx.AsyncClient) -> None:
        self.config = config
        self._client = client
        self._jwks: dict[str, dict[str, Any]] = {}
        self._jwks_fetched_at: datetime | None = None

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.config.client_id,
                "redirect_uri": self.config.redirect_uri,
                "scope": self.config.scope,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self.config.authorization_endpoint}?{query}"

    async def exchange(
        self, code: str, *, code_verifier: str, nonce: str, now: datetime
    ) -> IdTokenClaims:
        try:
            response = await self._client.post(
                self.config.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": self.config.redirect_uri,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                },
                timeout=10,
            )
        except httpx.HTTPError as exc:
            raise OidcError("token endpoint unreachable") from exc
        if response.status_code != 200:
            raise OidcError(f"token endpoint answered {response.status_code}")
        id_token = response.json().get("id_token")
        if not isinstance(id_token, str):
            raise OidcError("no id_token in the token response")
        return await self._validate(id_token, nonce=nonce, now=now)

    async def _signing_key(self, kid: str, *, now: datetime) -> Any:
        stale = self._jwks_fetched_at is None or now - self._jwks_fetched_at >= JWKS_TTL
        if stale or kid not in self._jwks:  # unknown kid: the provider may have rotated keys
            try:
                response = await self._client.get(self.config.jwks_uri, timeout=10)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise OidcError("JWKS unreachable") from exc
            self._jwks = {key["kid"]: key for key in response.json()["keys"] if "kid" in key}
            self._jwks_fetched_at = now
        if kid not in self._jwks:
            raise OidcError("unknown signing key")
        return jwt.PyJWK(self._jwks[kid], algorithm=ALGORITHM).key

    async def _validate(self, token: str, *, nonce: str, now: datetime) -> IdTokenClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise OidcError("malformed id_token") from exc
        if header.get("alg") != ALGORITHM or not isinstance(header.get("kid"), str):
            raise OidcError("unexpected id_token algorithm")
        key = await self._signing_key(header["kid"], now=now)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=self.config.client_id,
                issuer=list(self.config.issuers),
                # Times are checked below against the injected clock.
                options={
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                    "require": ["iss", "aud", "sub", "exp", "iat", "nonce"],
                },
            )
        except jwt.PyJWTError as exc:
            raise OidcError("invalid id_token") from exc
        timestamp = now.timestamp()
        skew = CLOCK_SKEW.total_seconds()
        if claims["exp"] <= timestamp - skew or claims["iat"] > timestamp + skew:
            raise OidcError("id_token expired or not yet valid")
        if not hmac.compare_digest(str(claims["nonce"]), nonce):
            raise OidcError("nonce mismatch")
        email = claims.get("email")
        return IdTokenClaims(
            sub=str(claims["sub"]),
            email=email.lower() if isinstance(email, str) else None,
            email_verified=_flag(claims.get("email_verified")),
            is_private_email=_flag(claims.get("is_private_email")),
        )
