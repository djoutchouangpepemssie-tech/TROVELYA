"""Daily expiry of listings (P2-T04d, section 9.1, plan Q15).

An active listing whose `expires_at` has come leaves the shop window by the platform, one
transition at a time through the state machine (history, `listing.withdrawn` event), never a
bulk update of the status. A batch per transaction; a listing its seller is changing right now
is skipped (SKIP LOCKED) and expires at the next run. This job is a boundary: it commits.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.service.states import SYSTEM, apply_transition
from trovelya.modules.catalog.state_machine import ListingEvent
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)

BATCH = 500


async def expire_listings(
    sessionmaker: async_sessionmaker[AsyncSession], *, clock: Clock, batch: int = BATCH
) -> int:
    """The number of listings expired by this run."""
    now = clock.now()
    expired = 0
    while True:
        async with sessionmaker() as db:
            due = await repository.lock_due_listings(db, now=now, limit=batch)
            for listing_id in due:
                await apply_transition(
                    db,
                    listing_id=listing_id,
                    event=ListingEvent.EXPIRE,
                    actor=SYSTEM,
                    clock=clock,
                    reason_code="expired",
                )
            await commit(db)
        expired += len(due)
        if len(due) < batch:
            break
    logger.info("listings.expired", count=expired)
    return expired
