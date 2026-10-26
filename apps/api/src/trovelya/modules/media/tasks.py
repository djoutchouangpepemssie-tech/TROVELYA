"""Worker jobs of the media module, registered in trovelya.workers.main.

arq retries a job only when it raises `Retry`: a failed attempt (storage or database
unreachable, timeout of one image) is retried with a growing delay; the last one gives up and
rejects the media, so it never stays `processing`.
"""

import asyncio
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
# arq's own limit for one attempt. When it is reached arq neither retries nor lets us give up,
# so the attempt bounds itself a little earlier (waiting for the image slot included) and
# goes through the retry path below.
PROCESS_TIMEOUT_S = 120
_ATTEMPT_BUDGET_S = PROCESS_TIMEOUT_S - 20


async def process_media_job(ctx: dict[str, Any], media_id: str) -> str:
    """Enqueued by `complete` after commit; safe to replay (see processing.py)."""
    media = UUID(media_id)
    attempt: int = ctx["job_try"]
    try:
        async with asyncio.timeout(_ATTEMPT_BUDGET_S):
            return await process_media(
                ctx["sessionmaker"], ctx["storage"], media, image_slot=ctx.get("image_slot")
            )
    except Exception as exc:
        if attempt >= MAX_TRIES:
            logger.error("media.processing_abandoned", media_id=media_id, error=repr(exc))
            # Should this fail too (database unreachable), arq records the job as failed and
            # the recovery cron picks the media up.
            return await fail_media(ctx["sessionmaker"], ctx["storage"], media)
        logger.warning("media.processing_retry", media_id=media_id, attempt=attempt)
        # 30 s, then 2 min: a short storage outage does not cost the member their photos.
        raise Retry(defer=30 * 4 ** (attempt - 1)) from exc


async def recover_stuck_media_job(ctx: dict[str, Any]) -> int:
    return await recover_stuck_media(
        ctx["sessionmaker"], ctx["storage"], ctx["redis"], clock=ctx["clock"]
    )
