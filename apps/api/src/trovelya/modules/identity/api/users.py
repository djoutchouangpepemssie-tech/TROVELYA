"""Public member profiles (`/v1/users/*`), visible without signing in."""

from fastapi import APIRouter

from trovelya.modules.identity.schemas import PublicProfile
from trovelya.modules.identity.service import profile
from trovelya.modules.identity.service.auth import Uow

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/{username}", operation_id="users_get_public")
async def get_public_profile(username: str, db: Uow) -> PublicProfile:
    """404 for an unknown name, an account not active or restricted, a profile not yet
    completed, or an account whose erasure was requested."""
    row = await profile.public_profile(db, username)
    return PublicProfile.model_validate(row, from_attributes=True)
