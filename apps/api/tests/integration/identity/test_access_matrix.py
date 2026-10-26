"""Access matrix of the API routes (P1 gate, G2, section 13.3).

Every route is declared below, in one group; a new route that is not makes the first test
fail, so its access rule is thought about once. Open to anybody:
- PUBLIC_ROUTES need nobody signed in (sign-in itself, health, public links);
- OPTIONAL_ROUTES answer anybody, and the signed-in member about themselves only (their
  consents, the methods open to them, a public profile seen by them).
Signed-in members only:
- SELF_ROUTES act on the caller's own account only (no other member's resource in the path);
- OWNED_ROUTES name a resource in the path: someone else's is answered 404, as if it did not
  exist (no way to learn that it does);
- STAFF_ROUTES need a staff session: a member is answered 403.
Anonymous callers get 401 on all of them.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import TEST_PROXY_SECRET, TEST_SECRET, make_settings
from tests.integration.identity.test_places import ADDRESS, ZONE
from tests.integration.identity.test_profile import POLICY, T0, Account, make_account
from tests.routes import api_routes
from trovelya.core.csrf import CSRF_COOKIE, issue_csrf_token
from trovelya.core.flags import FlagService
from trovelya.main import create_app
from trovelya.modules.identity.service import create_session
from trovelya.modules.identity.service.auth import current_user, optional_user
from trovelya.modules.identity.service.gdpr import build_data_export
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id

SELF_ROUTES = {
    "GET /v1/me",
    "PATCH /v1/me",
    "GET /v1/me/username-suggestion",
    "POST /v1/me/complete-profile",
    "POST /v1/me/email",
    "POST /v1/auth/logout",
    "GET /v1/me/sessions",
    "DELETE /v1/me/sessions",
    "POST /v1/me/data-export",
    "GET /v1/me/data-requests",
    "POST /v1/me/erasure",
    "POST /v1/me/erasure/cancel",
    "GET /v1/me/blocks",
    "GET /v1/me/passkeys",
    "POST /v1/auth/passkeys/register/options",
    "POST /v1/auth/passkeys/register/verify",
    "POST /v1/auth/step-up/options",
    "POST /v1/auth/step-up",
    "POST /v1/auth/step-up/verify",
    "GET /v1/geo/search",
    "GET /v1/geo/reverse",
    "GET /v1/me/addresses",
    "POST /v1/me/addresses",
    "GET /v1/me/zones",
    "POST /v1/me/zones",
    "GET /v1/me/preferences",
    "PUT /v1/me/preferences",
    # The member in the path is the one followed or blocked, a relation of the caller's own.
    "POST /v1/users/{user_id}/follow",
    "DELETE /v1/users/{user_id}/follow",
    "POST /v1/users/{user_id}/block",
    "DELETE /v1/users/{user_id}/block",
}
OWNED_ROUTES = {
    "DELETE /v1/me/sessions/{session_id}",
    "GET /v1/me/data-export/{request_id}/download",
    "PATCH /v1/me/passkeys/{passkey_id}",
    "DELETE /v1/me/passkeys/{passkey_id}",
    "PATCH /v1/me/addresses/{address_id}",
    "DELETE /v1/me/addresses/{address_id}",
    "PATCH /v1/me/zones/{zone_id}",
    "DELETE /v1/me/zones/{zone_id}",
}
STAFF_ROUTES = {
    "GET /v1/staff/approvals",
    "POST /v1/staff/approvals/{approval_id}/approve",
    "POST /v1/staff/approvals/{approval_id}/reject",
    "POST /v1/staff/roles/requests",
}
PRIVATE_ROUTES = SELF_ROUTES | OWNED_ROUTES | STAFF_ROUTES
OPTIONAL_ROUTES = {
    "GET /v1/auth/methods",
    "GET /v1/me/consents",
    "POST /v1/me/consents",
    "GET /v1/users/{username}",
}
PUBLIC_ROUTES = {
    "GET /health",
    "GET /ready",
    "GET /v1/csrf",
    "POST /v1/auth/magic-link",
    "POST /v1/auth/magic-link/verify",
    "POST /v1/auth/email-change/verify",  # the e-mailed token is the proof
    "GET /v1/auth/oauth/{provider}/start",
    "GET /v1/auth/oauth/{provider}/callback",
    "POST /v1/auth/oauth/{provider}/callback",
    "GET /v1/auth/oauth/{provider}/finish",
    "POST /v1/auth/passkeys/login/options",
    "POST /v1/auth/passkeys/login/verify",
    "POST /v1/auth/passkeys/enrol/options",  # the enrolment token is the proof
    "POST /v1/auth/passkeys/enrol/verify",
    "GET /v1/categories",
    "GET /v1/brands",
}

# A valid body for the routes that read one (none is reached by a refused caller anyway).
BODIES: dict[str, dict[str, Any]] = {
    "PATCH /v1/me/passkeys/{passkey_id}": {"name": "Pris"},
    "PATCH /v1/me/addresses/{address_id}": {"city": "Ailleurs"},
    "PATCH /v1/me/zones/{zone_id}": {"label": "Ailleurs"},
}


class _NoQueue:
    """Jobs (e-mails, exports) are not run here; the export is built by the test itself."""

    async def enqueue_job(self, function: str, *args: object) -> None:
        return None


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client: Redis
) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings())
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis_client
    app.state.clock = FixedClock(T0)
    app.state.flags = FlagService(sessionmaker, redis_client, {"auth.passkeys": True})
    app.state.queue = _NoQueue()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
    ) as c:
        c.headers.update({"x-trv-proxy-secret": TEST_PROXY_SECRET})
        yield c


def _production_routes() -> dict[str, set[str]]:
    """Every route as deployed (test-only routes are left out), by what it asks of the caller."""
    app = create_app(make_settings(env="production"))
    groups: dict[str, set[str]] = {"private": set(), "optional": set(), "public": set()}
    for route in api_routes(app):
        group = (
            "private"
            if route.depends_on(current_user)
            else "optional"
            if route.depends_on(optional_user)
            else "public"
        )
        groups[group].add(route.key)
    return groups


def _url(key: str, ids: dict[str, UUID]) -> tuple[str, str]:
    method, path = key.split(" ", 1)
    for name, value in ids.items():
        path = path.replace("{" + name + "}", str(value))
    return method, path


async def _call(
    client: AsyncClient, key: str, ids: dict[str, UUID], headers: dict[str, str]
) -> int:
    method, url = _url(key, ids)
    body = BODIES.get(key, {}) if method in {"POST", "PUT", "PATCH"} else None
    response = await client.request(method, url, headers=headers, json=body)
    return response.status_code


def _random_ids() -> dict[str, UUID]:
    return {
        name: new_id()
        for name in (
            "user_id",
            "session_id",
            "request_id",
            "passkey_id",
            "address_id",
            "zone_id",
            "approval_id",
        )
    }


def test_every_route_is_declared() -> None:
    routes = _production_routes()
    declared = {"private": PRIVATE_ROUTES, "optional": OPTIONAL_ROUTES, "public": PUBLIC_ROUTES}
    for group, found in routes.items():
        assert sorted(found - declared[group]) == [], f"declare these {group} routes"
        assert sorted(declared[group] - found) == [], f"these {group} routes are not that"
    assert not (SELF_ROUTES & OWNED_ROUTES or SELF_ROUTES & STAFF_ROUTES)


async def test_anonymous_gets_401_everywhere(client: AsyncClient) -> None:
    # A CSRF token without a session: the refusal is about who calls, never about CSRF.
    csrf = issue_csrf_token(TEST_SECRET)
    headers = {"cookie": f"{CSRF_COOKIE}={csrf}", "x-csrf-token": csrf}
    ids = _random_ids()
    answers = {key: await _call(client, key, ids, headers) for key in sorted(PRIVATE_ROUTES)}
    assert {key: status for key, status in answers.items() if status != 401} == {}


async def _owned_resources(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient, owner: Account
) -> dict[str, UUID]:
    """One of each resource the OWNED_ROUTES name, all belonging to `owner`."""
    async with sessionmaker() as db:
        other_device = await create_session(
            db,
            user_id=owner.id,
            kind="web",
            ip="203.0.113.8",
            user_agent=None,
            country="FR",
            strong=False,
            policy=POLICY,
            clock=FixedClock(T0),
        )
        passkey_id = new_id()
        await db.execute(
            text(
                "INSERT INTO passkeys (id, user_id, credential_id, public_key, sign_count, name)"
                " VALUES (:id, :u, :cred, '\\x0304'::bytea, 0, 'Téléphone')"
            ),
            {"id": passkey_id, "u": owner.id, "cred": passkey_id.bytes},
        )
        await db.commit()
    address = await client.post("/v1/me/addresses", headers=owner.headers, json=ADDRESS)
    zone = await client.post("/v1/me/zones", headers=owner.headers, json=ZONE)
    export = await client.post("/v1/me/data-export", headers=owner.headers)
    consent = await client.post(
        "/v1/me/consents",
        headers=owner.headers,
        json={"purpose": "location", "granted": True, "policy_version": "v1"},
    )
    assert consent.status_code == 201
    assert (address.status_code, zone.status_code, export.status_code) == (201, 201, 202)
    request_id = UUID(export.json()["request_id"])
    built = await build_data_export(
        sessionmaker, request_id, settings=make_settings(), clock=FixedClock(T0), queue=_NoQueue()
    )
    assert built
    return {
        "session_id": other_device.session_id,
        "request_id": request_id,
        "passkey_id": passkey_id,
        "address_id": UUID(address.json()["id"]),
        "zone_id": UUID(zone.json()["id"]),
    }


async def test_someone_elses_resources_answer_404(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    owner = await make_account(sessionmaker, completed=True)
    intruder = await make_account(sessionmaker, completed=True)  # strong sign-in, like owner
    ids = await _owned_resources(sessionmaker, client, owner)

    answers = {key: await _call(client, key, ids, intruder.headers) for key in sorted(OWNED_ROUTES)}
    assert {key: status for key, status in answers.items() if status != 404} == {}

    # The intruder's own lists never show the owner's resources.
    owned = {str(value) for value in ids.values()} | {str(owner.id)}
    for listing in (
        "/v1/me/sessions",
        "/v1/me/data-requests",
        "/v1/me/passkeys",
        "/v1/me/addresses",
        "/v1/me/zones",
    ):
        answer = await client.get(listing, headers=intruder.headers)
        assert answer.status_code == 200, listing
        assert not [value for value in owned if value in answer.text], listing
    # Consents carry no identifier: the owner's choice must simply not show up.
    consents = (await client.get("/v1/me/consents", headers=intruder.headers)).json()
    assert consents["consents"] == []

    # Nothing was touched, and the routes do work for the owner (a 404 for all proves nothing).
    for key in sorted(OWNED_ROUTES, key=lambda k: k.startswith("DELETE")):  # deletions last
        assert await _call(client, key, ids, owner.headers) in {200, 204}, key


async def test_members_get_403_on_staff_routes(
    sessionmaker: async_sessionmaker[AsyncSession], client: AsyncClient
) -> None:
    member = await make_account(sessionmaker, completed=True)
    ids = _random_ids()
    answers = {key: await _call(client, key, ids, member.headers) for key in sorted(STAFF_ROUTES)}
    assert {key: status for key, status in answers.items() if status != 403} == {}
