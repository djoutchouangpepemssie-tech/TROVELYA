"""OpenID Connect adapter: authorization URL, PKCE and ID token validation (P1-T03, 13.2)."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.fake_oidc import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, FakeIdp, fake_config
from trovelya.modules.identity.adapters.oidc import OidcError, OidcProvider, new_pkce

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp(T0)


@pytest.fixture
def provider(idp: FakeIdp) -> OidcProvider:
    return OidcProvider(fake_config(), idp.client())


async def _exchange(provider: OidcProvider, *, nonce: str = "nonce-1", now: datetime = T0):
    return await provider.exchange("the-code", code_verifier="verifier", nonce=nonce, now=now)


def test_pkce_challenge_is_s256_of_verifier() -> None:
    verifier, challenge = new_pkce()
    assert 43 <= len(verifier) <= 128
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == digest.decode()


def test_authorization_url(provider: OidcProvider) -> None:
    url = urlsplit(provider.authorization_url(state="st", nonce="nc", code_challenge="ch"))
    assert f"{url.scheme}://{url.netloc}{url.path}" == fake_config().authorization_endpoint
    assert {k: v[0] for k, v in parse_qs(url.query).items()} == {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile",
        "state": "st",
        "nonce": "nc",
        "code_challenge": "ch",
        "code_challenge_method": "S256",
    }


async def test_valid_token_and_pkce_verifier_sent(idp: FakeIdp, provider: OidcProvider) -> None:
    idp.next_token = idp.id_token()
    claims = await _exchange(provider)
    assert (claims.sub, claims.email, claims.email_verified) == (
        "google-sub-1",
        "membre@example.org",
        True,
    )
    assert claims.is_private_email is False
    [form] = idp.token_requests
    assert {k: v[0] for k, v in form.items()} == {
        "grant_type": "authorization_code",
        "code": "the-code",
        "code_verifier": "verifier",
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }


async def test_email_verified_as_string(idp: FakeIdp, provider: OidcProvider) -> None:
    idp.next_token = idp.id_token(email_verified="true", is_private_email="true")
    claims = await _exchange(provider)
    assert claims.email_verified is True and claims.is_private_email is True


async def test_jwks_cached_one_hour(idp: FakeIdp, provider: OidcProvider) -> None:
    idp.next_token = idp.id_token()
    await _exchange(provider)
    await _exchange(provider, now=T0 + timedelta(minutes=30))
    assert idp.jwks_requests == 1
    idp.now = T0 + timedelta(minutes=61)
    idp.next_token = idp.id_token()
    await _exchange(provider, now=idp.now)
    assert idp.jwks_requests == 2


@pytest.mark.parametrize(
    ("case", "kwargs"),
    [
        ("bad_signature", {"key": rsa.generate_private_key(public_exponent=65537, key_size=2048)}),
        ("wrong_iss", {"iss": "https://evil.example.test"}),
        ("wrong_aud", {"aud": "someone-else"}),
        ("expired", {"expires_in": timedelta(minutes=-5)}),
        ("nonce_mismatch", {"nonce": "other-nonce"}),
        ("hmac_algorithm", {"algorithm": "HS256"}),
        ("no_email_verified", {"email_verified": "false"}),
    ],
)
async def test_invalid_id_token_rejected(
    idp: FakeIdp, provider: OidcProvider, case: str, kwargs: dict[str, object]
) -> None:
    idp.next_token = idp.id_token(**kwargs)  # pyright: ignore[reportArgumentType]
    if case == "no_email_verified":
        # Not an invalid token: the claim is reported as is, the service decides.
        assert (await _exchange(provider)).email_verified is False
        return
    with pytest.raises(OidcError):
        await _exchange(provider)


async def test_token_endpoint_error(idp: FakeIdp, provider: OidcProvider) -> None:
    idp.token_status = 400
    with pytest.raises(OidcError):
        await _exchange(provider)


async def test_missing_id_token(idp: FakeIdp, provider: OidcProvider) -> None:
    idp.next_token = None
    with pytest.raises(OidcError):
        await _exchange(provider)
