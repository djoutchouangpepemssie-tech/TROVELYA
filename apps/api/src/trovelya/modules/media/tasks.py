"""Worker jobs of the media module, registered in trovelya.workers.main."""

from typing import Any
from uuid import UUID

from trovelya.modules.media.service.processing import process_media
from trovelya.modules.media.service.uploads import PROCESS_JOB

__all__ = ["PROCESS_JOB", "PROCESS_TIMEOUT_S", "process_media_job"]

# One attempt: reading, one image (60 s at most) and writing its variants.
PROCESS_TIMEOUT_S = 120


async def process_media_job(ctx: dict[str, Any], media_id: str) -> str:
    """Enqueued by `complete` after commit; safe to replay (see processing.py)."""
    return await process_media(
        ctx["sessionmaker"], ctx["storage"], UUID(media_id), image_slot=ctx.get("image_slot")
    )
