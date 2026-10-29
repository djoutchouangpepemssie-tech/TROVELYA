"""Who may do what with listings (plan P2 Q1)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.identity.service import trade_refusal
from trovelya.shared.clock import Clock


async def publish_refusal(db: AsyncSession, user_id: UUID, *, clock: Clock) -> str | None:
    """`can_publish_listing` of Q1: why the member may not put a listing online
    (`profile_incomplete`, `too_young`, `account_restricted`), None when they may. From P4, the
    `listing.publish` permission (seller activation) is required as well."""
    return await trade_refusal(db, user_id, clock=clock)
