"""Media routes (`/v1/media/*`, section 11.5): uploads straight to storage (ADR-0019)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from trovelya.core.db import Uow
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity.service import CurrentUser, get_clock
from trovelya.modules.identity.service.auth import completed_user
from trovelya.modules.media.adapters.storage import ObjectStorage
from trovelya.modules.media.schemas import MediaOut, UploadIn, UploadOut
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


@router.post(
    "/{media_id}/complete",
    operation_id="media_complete",
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"description": "Not the caller's"}, 409: {"description": "Already processed: ready or rejected"}},
)
async def post_complete(media_id: UUID, request: Request, db: Uow, me: Member) -> MediaOut:
    """The file is in storage: the worker checks and processes it."""
    await uploads.complete_upload(
        db, owner_id=me.id, media_id=media_id, queue=request.app.state.queue
    )
    return await uploads.get_media(
        db,
        owner_id=me.id,
        media_id=media_id,
        public_url=request.app.state.settings.media_public_url,
    )


@router.get(
    "/{media_id}", operation_id="media_get", responses={404: {"description": "Not the caller's"}}
)
async def get_media(media_id: UUID, request: Request, db: Uow, me: Member) -> MediaOut:
    return await uploads.get_media(
        db,
        owner_id=me.id,
        media_id=media_id,
        public_url=request.app.state.settings.media_public_url,
    )
