"""Worker jobs of the media module, registered in trovelya.workers.main.

arq retries a job only when it raises `Retry`: a failed attempt (storage or database
unreachable, timeout of one image) is retried with a growing delay; the last one gives up and
rejects the media, so it never stays `processing`.
"""

from typing import Any
from uuid import UUID

import structlog
from arq import Retry

from trovelya.modules.media.service.processing import (
    fail_media,
    process_media,
    recover_stuck_media,
)
from trovelya.modules.media.service.uploads import PROCESS_JOB

__all__ = ["MAX_TRIES", "PROCESS_JOB", "PROCESS_TIMEOUT_S", "process_media_job"]

logger = structlog.get_logger(__name__)

MAX_TRIES = 3
# One attempt: reading, one image (60 s at most) and writing its variants.
PROCESS_TIMEOUT_S = 120


async def process_media_job(ctx: dict[str, Any], media_id: str) -> str:
    """Enqueued by `complete` after commit; safe to replay (see processing.py)."""
    media = UUID(media_id)
    attempt: int = ctx["job_try"]
    try:
        return await process_media(
            ctx["sessionmaker"], ctx["storage"], media, image_slot=ctx.get("image_slot")
        )
    except Exception as exc:
        if attempt >= MAX_TRIES:
            logger.error("media.processing_abandoned", media_id=media_id, error=repr(exc))
            return await fail_media(ctx["sessionmaker"], ctx["storage"], media)
        logger.warning("media.processing_retry", media_id=media_id, attempt=attempt)
        raise Retry(defer=2**attempt) from exc


async def recover_stuck_media_job(ctx: dict[str, Any]) -> int:
    return await recover_stuck_media(ctx["sessionmaker"], ctx["storage"], clock=ctx["clock"])
