"""Test-only identity routes: mounted when ENV is "local" or "test", never elsewhere.

`POST /v1/_test/session` creates a member and signs the browser in, so end-to-end tests do not
go through e-mails; `POST /v1/_test/staff-enrolment` creates a staff account and returns its
enrolment link, as the creation script prints it; `POST /v1/_test/magic-link` returns the
sign-in link the e-mail would carry (or an already expired one); `POST /v1/_test/step-up-link`
and `POST /v1/_test/email-change-link` return the links e-mailed to the signed-in member;
`POST /v1/_test/flag-allow` adds the signed-in member to a flag's allow list (one test's account,
never the others running in parallel).
Nothing here exists on staging or in production.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from trovelya.core.flags import CACHE_PREFIX
from trovelya.modules.identity import repository
from trovelya.modules.identity.service import (
    CurrentUser,
    SessionPolicy,
    create_session,
    current_user,
    get_clock,
    get_session_policy,
    set_session_cookie,
)
from trovelya.modules.identity.service.auth import Uow
from trovelya.modules.identity.service.email_change import issue_email_change_link
from trovelya.modules.identity.service.magic_links import issue_magic_link, provisional_username
from trovelya.modules.identity.service.staff_accounts import issue_staff_enrolment
from trovelya.modules.identity.service.step_up import issue_step_up_link
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

router = APIRouter(prefix="/v1/_test", tags=["test"], include_in_schema=False)

_COMPLETE = text("UPDATE users SET birth_year = 1990, profile_completed_at = :now WHERE id = :id")


class TestSessionRequest(BaseModel):
    completed: bool = False  # True: profile already completed (skips the onboarding)
    strong: bool = True  # False: no recent strong proof, sensitive actions ask for step-up
    email: str | None = Field(default=None, max_length=254)


class TestSession(BaseModel):
    user_id: str
    email: str


@router.post("/session", operation_id="test_session")
async def test_session(
    body: TestSessionRequest,
    response: Response,
    db: Uow,
    clock: Annotated[Clock, Depends(get_clock)],
    policy: Annotated[SessionPolicy, Depends(get_session_policy)],
) -> TestSession:
    now = clock.now()
    user_id = new_id()
    email = body.email or f"e2e-{user_id.hex}@example.org"
    await repository.create_user(
        db,
        user_id=user_id,
        email=email,
        username=provisional_username(),
        display_name="Membre",
        now=now,
    )
    if body.completed:
        await db.execute(_COMPLETE, {"id": user_id, "now": now})
    issued = await create_session(
        db,
        user_id=user_id,
        kind="web",
        ip=None,
        user_agent=None,
        country="FR",
        strong=body.strong,
        policy=policy,
        clock=clock,
    )
    set_session_cookie(response, issued, clock=clock)
    return TestSession(user_id=str(user_id), email=email)


class TestStaffEnrolment(BaseModel):
    user_id: str
    link: str


@router.post("/staff-enrolment", operation_id="test_staff_enrolment")
async def test_staff_enrolment(
    request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> TestStaffEnrolment:
    enrolment = await issue_staff_enrolment(
        request.app.state.sessionmaker,
        request.app.state.redis,
        email=f"e2e-staff-{new_id().hex}@example.org",
        role="staff_superadmin",
        settings=request.app.state.settings,
        clock=clock,
    )
    return TestStaffEnrolment(user_id=str(enrolment.user_id), link=enrolment.link)


class TestMagicLinkRequest(BaseModel):
    email: str = Field(max_length=254)
    expired: bool = False


class TestMagicLink(BaseModel):
    link: str


@router.post("/magic-link", operation_id="test_magic_link")
async def test_magic_link(
    body: TestMagicLinkRequest,
    request: Request,
    db: Uow,
    clock: Annotated[Clock, Depends(get_clock)],
) -> TestMagicLink:
    link, _ = await issue_magic_link(
        db,
        email=body.email,
        ip=None,
        settings=request.app.state.settings,
        clock=clock,
        ttl=timedelta(minutes=-1) if body.expired else None,
    )
    return TestMagicLink(link=link)


class TestLink(BaseModel):
    link: str


class TestEmailChangeRequest(BaseModel):
    new_email: str = Field(max_length=254)


@router.post("/step-up-link", operation_id="test_step_up_link")
async def test_step_up_link(
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(current_user)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> TestLink:
    link, _, _ = await issue_step_up_link(
        db, user_id=user.id, ip="unknown", settings=request.app.state.settings, clock=clock
    )
    return TestLink(link=link)


@router.post("/email-change-link", operation_id="test_email_change_link")
async def test_email_change_link(
    body: TestEmailChangeRequest,
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(current_user)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> TestLink:
    issued = await issue_email_change_link(
        db,
        user_id=user.id,
        new_email=body.new_email,
        ip="unknown",
        settings=request.app.state.settings,
        clock=clock,
    )
    if issued is None:
        raise HTTPException(status_code=409, detail="email in use")
    return TestLink(link=issued[0])


class TestFlagAllow(BaseModel):
    key: str = Field(max_length=100)


# A flag first written here keeps its configured default for everyone else; a member is listed
# once however many times a test asks.
_ALLOW = text(
    "INSERT INTO feature_flags (key, enabled, allow_user_ids)"
    " VALUES (:key, :enabled, ARRAY[CAST(:id AS uuid)])"
    " ON CONFLICT (key) DO UPDATE"
    " SET allow_user_ids = array_append(feature_flags.allow_user_ids, CAST(:id AS uuid))"
    " WHERE NOT CAST(:id AS uuid) = ANY(feature_flags.allow_user_ids)"
)


@router.post("/flag-allow", operation_id="test_flag_allow", status_code=204)
async def test_flag_allow(
    body: TestFlagAllow,
    request: Request,
    db: Uow,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> None:
    enabled = request.app.state.settings.feature_flags_default.get(body.key, False)
    await db.execute(_ALLOW, {"key": body.key, "id": user.id, "enabled": enabled})
    await request.app.state.redis.delete(CACHE_PREFIX + body.key)
