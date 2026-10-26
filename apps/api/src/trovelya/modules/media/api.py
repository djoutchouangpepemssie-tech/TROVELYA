"""Media routes (`/v1/media/*`, section 11.5): uploads straight to storage (ADR-0019)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from trovelya.core.db import Uow
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.service import CurrentUser, get_clock
from trovelya.modules.identity.service.auth import completed_user
from trovelya.modules.media.adapters.storage import ObjectStorage
from trovelya.modules.media.schemas import UploadIn, UploadOut
from trovelya.modules.media.service import uploads
from trovelya.shared.clock import Clock

router = APIRouter(prefix="/v1/media", tags=["media"])

Member = Annotated[CurrentUser, Depends(completed_user)]
# Off until R2 is checked in staging and media are erased with the account (P2-T02c):
# before that, a closed account would leave its photos behind.
UPLOADS_FLAG = "media.uploads"


def get_storage(request: Request) -> ObjectStorage:
    return request.app.state.storage


@router.post(
    "/uploads",
    operation_id="media_upload",
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Flag media.uploads off"},
        413: {"description": "Larger than media.max_image_bytes"},
        422: {"description": "Type not accepted"},
        429: {"description": "media.uploads_per_hour or _per_day reached"},
    },
)
async def post_upload(
    body: UploadIn,
    request: Request,
    db: Uow,
    me: Member,
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> UploadOut:
    """A 5-minute URL to PUT the file to, with its exact type and size."""
    if not await request.app.state.flags.is_enabled(UPLOADS_FLAG, user_id=me.id):
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return await uploads.request_upload(db, owner_id=me.id, body=body, storage=storage, clock=clock)
