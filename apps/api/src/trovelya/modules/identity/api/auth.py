"""Sign-in and sign-out routes (`/v1/auth/*`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from trovelya.modules.identity.service import (
    CurrentUser,
    clear_session_cookie,
    current_user,
    get_clock,
    revoke_session,
)
from trovelya.modules.identity.service.auth import Uow
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/logout", operation_id="auth_logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: Uow,
    user: Annotated[CurrentUser, Depends(current_user)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> None:
    """Revoke the current session and clear its cookie."""
    await revoke_session(db, user_id=user.id, session_id=user.session_id, clock=clock)
    clear_session_cookie(response)
