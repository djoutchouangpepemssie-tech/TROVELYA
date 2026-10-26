"""Member profiles (`/v1/users/*`): public profiles, following and blocking."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from trovelya.modules.identity.schemas import AvatarVariant, PublicProfile, Relationship
from trovelya.modules.identity.service import CurrentUser, get_clock, optional_user, profile
from trovelya.modules.identity.service import social as social_service
from trovelya.modules.identity.service.auth import Uow, completed_user
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/users", tags=["users"])

Member = Annotated[CurrentUser, Depends(completed_user)]
ClockDep = Annotated[Clock, Depends(get_clock)]
_TARGET_RESPONSES: dict[int | str, dict[str, str]] = {
    404: {"description": "Unknown or hidden member, or a block in either direction"},
    422: {"description": "Oneself"},
}


@router.get("/{username}", operation_id="users_get_public")
async def get_public_profile(
    username: str,
    request: Request,
    db: Uow,
    viewer: Annotated[CurrentUser | None, Depends(optional_user)],
) -> PublicProfile:
    """404 for an unknown name, an account not active or restricted, a profile not yet
    completed, or an account whose erasure was requested. Visible to the people it blocks."""
    row = await profile.public_profile(db, username)
    avatar = await profile.public_avatar(
        db, row.avatar_media_id, media_public_url=request.app.state.settings.media_public_url
    )
    result = PublicProfile.model_validate(row, from_attributes=True).model_copy(
        update={"avatar": None if avatar is None else [AvatarVariant(**v) for v in avatar]}
    )
    if viewer is not None:
        relation = await social_service.relationship(db, viewer=viewer.id, target=row.id)
        result.viewer = Relationship(**relation)
    return result


@router.post(
    "/{user_id}/follow",
    operation_id="users_follow",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_TARGET_RESPONSES,
)
async def post_follow(user_id: UUID, db: Uow, me: Member, clock: ClockDep) -> None:
    await social_service.follow(db, me=me.id, target=user_id, clock=clock)


@router.delete(
    "/{user_id}/follow", operation_id="users_unfollow", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_follow(user_id: UUID, db: Uow, me: Member) -> None:
    await social_service.unfollow(db, me=me.id, target=user_id)


@router.post(
    "/{user_id}/block",
    operation_id="users_block",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_TARGET_RESPONSES,
)
async def post_block(user_id: UUID, db: Uow, me: Member, clock: ClockDep) -> None:
    """Also removes the follows in both directions; unblocking does not bring them back."""
    await social_service.block(db, me=me.id, target=user_id, clock=clock)


@router.delete(
    "/{user_id}/block", operation_id="users_unblock", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_block(user_id: UUID, db: Uow, me: Member) -> None:
    await social_service.unblock(db, me=me.id, target=user_id)
