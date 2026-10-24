"""A fake OpenID Connect provider for tests: RSA keys generated here, served by MockTransport."""

import json
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import RSAAlgorithm

from trovelya.modules.identity.adapters.oidc import AppleProvider, OidcConfig

ISSUER = "https://idp.example.test"
CLIENT_ID = "client-123.apps.example.test"
CLIENT_SECRET = "client-secret"
REDIRECT_URI = "https://web.example.test/api/v1/auth/oauth/google/callback"
KID = "key-1"


def fake_config() -> OidcConfig:
    return OidcConfig(
        name="google",
        issuers=(ISSUER,),
        authorization_endpoint=f"{ISSUER}/authorize",
        token_endpoint=f"{ISSUER}/token",
        jwks_uri=f"{ISSUER}/jwks",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
    )


APPLE_TEAM_ID = "TEAM123456"
APPLE_KEY_ID = "KEY1234567"
APPLE_KEY = ec.generate_private_key(ec.SECP256R1())


def fake_apple_provider(client: httpx.AsyncClient) -> AppleProvider:
    pem = APPLE_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    config = OidcConfig(
        name="apple",
        issuers=(ISSUER,),
        authorization_endpoint=f"{ISSUER}/authorize",
        token_endpoint=f"{ISSUER}/token",
        jwks_uri=f"{ISSUER}/jwks",
        client_id=CLIENT_ID,
        client_secret="",
        redirect_uri="https://web.example.test/api/v1/auth/oauth/apple/callback",
        scope="name email",
        response_mode="form_post",
    )
    return AppleProvider(
        config, client, team_id=APPLE_TEAM_ID, key_id=APPLE_KEY_ID, private_key=pem
    )


class FakeIdp:
    """Issues ID tokens; the next token endpoint answer is whatever `next_token` holds."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.token_requests: list[dict[str, list[str]]] = []
        self.jwks_requests = 0
        self.next_token: str | None = None
        self.token_status = 200

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}

    def id_token(
        self,
        *,
        sub: str = "google-sub-1",
        email: str | None = "membre@example.org",
        email_verified: bool | str = True,
        nonce: str = "nonce-1",
        iss: str = ISSUER,
        aud: str = CLIENT_ID,
        expires_in: timedelta = timedelta(hours=1),
        key: rsa.RSAPrivateKey | None = None,
        algorithm: str = "RS256",
        **extra: Any,
    ) -> str:
        claims: dict[str, Any] = {
            "iss": iss,
            "aud": aud,
            "sub": sub,
            "iat": int(self.now.timestamp()),
            "exp": int((self.now + expires_in).timestamp()),
            "nonce": nonce,
            "email_verified": email_verified,
            **extra,
        }
        if email is not None:
            claims["email"] = email
        signing_key: Any = key or self.key
        if algorithm.startswith("HS"):
            signing_key = "a-shared-secret-that-is-long-enough-for-hmac-sha256"
        return jwt.encode(claims, signing_key, algorithm=algorithm, headers={"kid": KID})

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/jwks":
            self.jwks_requests += 1
            return httpx.Response(200, json=self.jwks())
        if request.url.path == "/token":
            self.token_requests.append(parse_qs(request.content.decode()))
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": self.next_token, "token_type": "Bearer"})
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
