"""Sign-in with Google (P1-T03, section 13.2): state, PKCE, nonce, account rules."""

import base64
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, make_settings
from tests.fake_oidc import FakeIdp, fake_apple_provider, fake_config
from trovelya.core.csrf import SESSION_COOKIE
from trovelya.core.email import open_email
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.identity.adapters.oidc import OidcProvider
from trovelya.modules.identity.service.oauth import OAUTH_COOKIE
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
WEB = "https://web.example.test"
START = "/v1/auth/oauth/google/start"
CALLBACK = "/v1/auth/oauth/google/callback"


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, args))


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp(T0)


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


def _app(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    idp: FakeIdp,
    queue: RecordingQueue,
    *,
    enabled: bool,
) -> Any:
    app = create_app(make_settings(web_origin=WEB))
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = FixedClock(T0)
    app.state.queue = queue
    flags = {"auth.oauth_google": enabled, "auth.oauth_apple": enabled}
    app.state.flags = FlagService(sessionmaker, redis_client, flags)
    app.state.oidc = {
        "google": OidcProvider(fake_config(), idp.client()),
        "apple": fake_apple_provider(idp.client()),
    }
    return app


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    idp: FakeIdp,
    queue: RecordingQueue,
) -> AsyncIterator[AsyncClient]:
    app = _app(sessionmaker, redis_client, idp, queue, enabled=True)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


async def _start(client: AsyncClient) -> dict[str, str]:
    """Start a sign-in; returns the authorization request's parameters."""
    response = await client.get(START)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return {k: v[0] for k, v in query.items()}


async def _sign_in(client: AsyncClient, idp: FakeIdp, **claims: Any) -> Response:
    params = await _start(client)
    idp.next_token = idp.id_token(nonce=params["nonce"], **claims)
    return await client.get(CALLBACK, params={"code": "c", "state": params["state"]})


def _error(response: Response) -> str | None:
    location = response.headers["location"]
    query = parse_qs(urlsplit(location).query)
    return query["erreur"][0] if "erreur" in query else None


async def _user(
    sessionmaker: async_sessionmaker[AsyncSession],
    email: str,
    *,
    verified: bool = True,
    staff: bool = False,
) -> UUID:
    user_id = new_id()
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, username, display_name, is_staff,"
                " email_verified_at, profile_completed_at)"
                " VALUES (:id, :email, :u, 'Membre', :staff,"
                " CASE WHEN :verified THEN now() END, now())"
            ),
            {
                "id": user_id,
                "email": email,
                "u": f"u_{user_id.hex[-8:]}",
                "staff": staff,
                "verified": verified,
            },
        )
        await db.commit()
    return user_id


async def _scalar(sessionmaker: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return await db.scalar(text(sql), params)


def _email() -> str:
    return f"{new_id().hex}@example.org"


# --- Start ---------------------------------------------------------------------------------


async def test_start_redirects_with_pkce_and_binds_state_to_cookie(
    client: AsyncClient, redis_client: Redis
) -> None:
    params = await _start(client)
    assert params["code_challenge_method"] == "S256"
    assert params["nonce"] and params["code_challenge"]
    state_hash = hashlib.sha256(params["state"].encode()).hexdigest()
    assert client.cookies.get(OAUTH_COOKIE) == state_hash
    assert 0 < await redis_client.ttl(f"oauth:{state_hash}") <= 600
    # Neither the state nor the PKCE verifier appear in clear in Redis keys.
    keys = [key.decode() for key in await redis_client.keys("oauth:*")]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert all(params["state"] not in key for key in keys)


async def test_provider_disabled_404(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    idp: FakeIdp,
    queue: RecordingQueue,
) -> None:
    app = _app(sessionmaker, redis_client, idp, queue, enabled=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        assert (await c.get(START)).status_code == 404
        assert (await c.get(CALLBACK, params={"code": "c", "state": "s"})).status_code == 404


async def test_unknown_or_unconfigured_provider_404(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    assert (await client.get("/v1/auth/oauth/facebook/start")).status_code == 404
    # Apple without credentials (the default until an Apple Developer account exists).
    app = create_app(make_settings(web_origin=WEB))
    app.state.flags = FlagService(sessionmaker, redis_client, {"auth.oauth_apple": True})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        assert (await c.get("/v1/auth/oauth/apple/start")).status_code == 404


# --- Callback ------------------------------------------------------------------------------


async def test_new_account_created_and_signed_in(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, idp: FakeIdp
) -> None:
    email = _email()
    response = await _sign_in(client, idp, sub=f"sub-{email}", email=email)
    assert response.status_code == 302
    assert response.headers["location"] == f"{WEB}/fr/bienvenue"
    assert any(c.startswith(f"{SESSION_COOKIE}=") for c in response.headers.get_list("set-cookie"))
    user_id = await _scalar(sessionmaker, "SELECT id FROM users WHERE email = :e", e=email)
    assert await _scalar(
        sessionmaker, "SELECT email_verified_at IS NOT NULL FROM users WHERE id = :id", id=user_id
    )
    assert (
        await _scalar(
            sessionmaker,
            "SELECT provider_subject FROM auth_identities WHERE user_id = :id",
            id=user_id,
        )
        == f"sub-{email}"
    )
    # Google is not a strong sign-in: no mfa_at on the session.
    assert await _scalar(
        sessionmaker, "SELECT mfa_at IS NULL FROM sessions WHERE user_id = :id", id=user_id
    )
    events = await _scalar(
        sessionmaker,
        "SELECT array_agg(type ORDER BY type) FROM outbox_events WHERE aggregate_id = :id",
        id=user_id,
    )
    assert events == ["session.created", "user.registered"]


async def test_known_identity_signs_in_same_user(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, idp: FakeIdp
) -> None:
    email = _email()
    await _sign_in(client, idp, sub=f"sub-{email}", email=email)
    # Same Google account, even if its address changed since.
    client.cookies.clear()
    response = await _sign_in(client, idp, sub=f"sub-{email}", email=_email())
    assert _error(response) is None
    assert (
        await _scalar(
            sessionmaker,
            "SELECT count(*) FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.email = :e",
            e=email,
        )
        == 2
    )


async def test_links_existing_verified_email(
    sessionmaker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    idp: FakeIdp,
    queue: RecordingQueue,
) -> None:
    email = _email()
    user_id = await _user(sessionmaker, email)
    response = await _sign_in(client, idp, sub=f"sub-{email}", email=email)
    assert response.headers["location"] == f"{WEB}/fr"
    assert (
        await _scalar(
            sessionmaker, "SELECT count(*) FROM auth_identities WHERE user_id = :id", id=user_id
        )
        == 1
    )
    [(_, (sealed,))] = queue.jobs
    message = open_email(sealed, settings=make_settings(web_origin=WEB))
    assert message.to == email
    assert message.subject == "Google a été associé à votre compte TROVÉLYA"


async def test_refuses_link_unverified_email(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, idp: FakeIdp
) -> None:
    email = _email()
    user_id = await _user(sessionmaker, email, verified=False)
    response = await _sign_in(client, idp, sub=f"sub-{email}", email=email)
    assert _error(response) == "oauth_email_unverified"
    assert (
        await _scalar(
            sessionmaker, "SELECT count(*) FROM auth_identities WHERE user_id = :id", id=user_id
        )
        == 0
    )


async def test_provider_unverified_email_refused(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, idp: FakeIdp
) -> None:
    email = _email()
    response = await _sign_in(client, idp, sub=f"sub-{email}", email=email, email_verified=False)
    assert _error(response) == "oauth_email_unverified"
    assert await _scalar(sessionmaker, "SELECT count(*) FROM users WHERE email = :e", e=email) == 0


async def test_staff_account_refused(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, idp: FakeIdp
) -> None:
    email = _email()
    staff_id = await _user(sessionmaker, email, staff=True)
    response = await _sign_in(client, idp, sub=f"sub-{email}", email=email)
    assert _error(response) == "oauth_failed"
    for sql in (
        "SELECT count(*) FROM sessions WHERE user_id = :id",
        "SELECT count(*) FROM auth_identities WHERE user_id = :id",
    ):
        assert await _scalar(sessionmaker, sql, id=staff_id) == 0


async def test_state_single_use(client: AsyncClient, idp: FakeIdp) -> None:
    params = await _start(client)
    idp.next_token = idp.id_token(nonce=params["nonce"], sub="sub-replay", email=_email())
    query = {"code": "c", "state": params["state"]}
    cookie = client.cookies.get(OAUTH_COOKIE)
    assert _error(await client.get(CALLBACK, params=query)) is None
    client.cookies.clear()
    client.cookies.set(OAUTH_COOKIE, cookie or "")
    assert _error(await client.get(CALLBACK, params=query)) == "oauth_failed"


async def test_state_bound_to_browser_cookie(client: AsyncClient, idp: FakeIdp) -> None:
    params = await _start(client)
    idp.next_token = idp.id_token(nonce=params["nonce"], sub="sub-csrf", email=_email())
    client.cookies.clear()  # another browser: the victim of a login CSRF
    response = await client.get(CALLBACK, params={"code": "c", "state": params["state"]})
    assert _error(response) == "oauth_failed"
    assert idp.token_requests == []


async def test_nonce_mismatch_rejected(client: AsyncClient, idp: FakeIdp) -> None:
    params = await _start(client)
    idp.next_token = idp.id_token(nonce="not-the-one", sub="sub-nonce", email=_email())
    response = await client.get(CALLBACK, params={"code": "c", "state": params["state"]})
    assert _error(response) == "oauth_failed"
    assert not any(
        c.startswith(f"{SESSION_COOKIE}=") for c in response.headers.get_list("set-cookie")
    )


async def test_pkce_verifier_sent(client: AsyncClient, idp: FakeIdp) -> None:
    params = await _start(client)
    idp.next_token = idp.id_token(nonce=params["nonce"], sub="sub-pkce", email=_email())
    await client.get(CALLBACK, params={"code": "c", "state": params["state"]})
    [form] = idp.token_requests
    verifier = form["code_verifier"][0]
    digest = hashlib.sha256(verifier.encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == params["code_challenge"]


async def test_consent_cancelled_or_missing_code(client: AsyncClient) -> None:
    params = await _start(client)
    response = await client.get(
        CALLBACK, params={"error": "access_denied", "state": params["state"]}
    )
    assert response.headers["location"] == f"{WEB}/fr/connexion?erreur=oauth_failed"
    assert any(c.startswith(f"{OAUTH_COOKIE}=") for c in response.headers.get_list("set-cookie"))


# --- Apple (form_post) ---------------------------------------------------------------------

APPLE_CALLBACK = "/v1/auth/oauth/apple/callback"


async def _apple_post(client: AsyncClient, idp: FakeIdp, **claims: Any) -> Response:
    """Start with Apple, then come back by a cross-site POST (no cookie sent)."""
    response = await client.get("/v1/auth/oauth/apple/start")
    params = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}
    assert params["response_mode"] == "form_post"
    idp.next_token = idp.id_token(nonce=params["nonce"], **claims)
    cookie = client.cookies.get(OAUTH_COOKIE) or ""
    client.cookies.clear()
    posted = await client.post(
        APPLE_CALLBACK, data={"code": "c", "state": params["state"], "user": "{}"}
    )
    client.cookies.set(OAUTH_COOKIE, cookie)
    return posted


def _finish_path(posted: Response) -> str:
    assert posted.status_code == 303
    location = posted.headers["location"]
    assert location.startswith(f"{WEB}/api/v1/auth/oauth/apple/finish?ref=")
    return location.removeprefix(f"{WEB}/api")


async def test_apple_form_post_then_finish(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, idp: FakeIdp
) -> None:
    email = _email()
    posted = await _apple_post(client, idp, sub=f"apple-{email}", email=email)
    finished = await client.get(_finish_path(posted))
    assert finished.headers["location"] == f"{WEB}/fr/bienvenue"
    assert any(c.startswith(f"{SESSION_COOKIE}=") for c in finished.headers.get_list("set-cookie"))
    assert (
        await _scalar(
            sessionmaker,
            "SELECT provider FROM auth_identities i JOIN users u ON u.id = i.user_id"
            " WHERE u.email = :e",
            e=email,
        )
        == "apple"
    )


async def test_apple_finish_ref_single_use_and_cookie_bound(
    client: AsyncClient, idp: FakeIdp
) -> None:
    posted = await _apple_post(client, idp, sub="apple-ref", email=_email())
    path = _finish_path(posted)
    client.cookies.clear()  # someone else opening the finish link
    assert _error(await client.get(path)) == "oauth_failed"
    assert _error(await client.get(path)) == "oauth_failed"  # and the reference is spent
    assert _error(await client.get("/v1/auth/oauth/apple/finish?ref=forged")) == "oauth_failed"


async def test_apple_private_relay_creates_account(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, idp: FakeIdp
) -> None:
    relay = f"{new_id().hex}@privaterelay.appleid.com"
    posted = await _apple_post(
        client,
        idp,
        sub=f"apple-{relay}",
        email=relay,
        email_verified="true",
        is_private_email="true",
    )
    finished = await client.get(_finish_path(posted))
    assert _error(finished) is None
    assert await _scalar(sessionmaker, "SELECT count(*) FROM users WHERE email = :e", e=relay) == 1


async def test_callback_method_must_match_provider(client: AsyncClient) -> None:
    assert (await client.get(APPLE_CALLBACK, params={"code": "c", "state": "s"})).status_code == 404
    assert (await client.post(CALLBACK, data={"code": "c", "state": "s"})).status_code == 404
    assert (await client.get("/v1/auth/oauth/google/finish?ref=x")).status_code == 404
