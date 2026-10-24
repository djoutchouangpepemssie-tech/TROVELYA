"""Test-only identity routes: mounted when ENV is "local" or "test", never elsewhere.

`POST /v1/_test/session` creates a member and signs the browser in, so end-to-end tests do not
go through e-mails; `POST /v1/_test/staff-enrolment` creates a staff account and returns its
enrolment link, as the creation script prints it. Nothing here exists on staging or in
production.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from trovelya.modules.identity import repository
from trovelya.modules.identity.service import (
    SessionPolicy,
    create_session,
    get_clock,
    get_session_policy,
    set_session_cookie,
)
from trovelya.modules.identity.service.auth import Uow
from trovelya.modules.identity.service.magic_links import provisional_username
from trovelya.modules.identity.service.staff_accounts import issue_staff_enrolment
from trovelya.shared.clock import Clock
from trovelya.shared.ids import new_id

router = APIRouter(prefix="/v1/_test", tags=["test"], include_in_schema=False)

_COMPLETE = text("UPDATE users SET birth_year = 1990, profile_completed_at = :now WHERE id = :id")


class TestSessionRequest(BaseModel):
    completed: bool = False  # True: profile already completed (skips the onboarding)
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
        strong=True,
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
