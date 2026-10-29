"""Who may do what with listings (plan P2 Q1)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.identity.service import may_trade
from trovelya.shared.clock import Clock


async def can_publish_listing(db: AsyncSession, user_id: UUID, *, clock: Clock) -> bool:
    """Q1: a completed profile, 18 or over (rule E14), not suspended, no erasure in progress.
    From P4, the `listing.publish` permission (seller activation) is required as well."""
    return await may_trade(db, user_id, clock=clock)
