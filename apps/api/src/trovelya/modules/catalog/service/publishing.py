"""Putting a listing online (P2-T04b, plan Q1, Q14, Q15, Q24). Never commits.

The seller's lock comes first, as for drafts: one write of a seller's listings at a time, so
two publications cannot both slip under the quota, and the photos are never taken in two
orders (no deadlock).
"""

import math
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.catalog import policies, repository
from trovelya.modules.catalog.models import ListingStatus
from trovelya.modules.catalog.schemas import ListingOut
from trovelya.modules.catalog.service.listings import own_listing
from trovelya.modules.catalog.service.states import Actor, apply_transition
from trovelya.modules.catalog.state_machine import TRANSITIONS, ListingEvent
from trovelya.shared.clock import Clock, FixedClock

QUOTA_WINDOW = timedelta(hours=24)


class ModerationGate(Protocol):
    """Which way a draft goes online: `publish` (low risk, at once) or `submit_for_review`."""

    async def route(self, db: AsyncSession, listing_id: UUID) -> ListingEvent: ...


class PublishEverything:
    """Until P2-T05b brings the moderation: every listing goes online at once."""

    async def route(self, db: AsyncSession, listing_id: UUID) -> ListingEvent:
        return ListingEvent.PUBLISH


async def check_publication_quota(db: AsyncSession, seller_id: UUID, *, clock: Clock) -> None:
    """Q24: 429 `publication_limit` once the seller has put `listings.max_publications_per_day`
    listings online over the last 24 hours (first publications, republications and renewals);
    `Retry-After` says when the oldest of them leaves the window."""
    now = clock.now()
    limit = await repository.setting_int(db, "listings.max_publications_per_day")
    window = await repository.put_online_since(db, seller_id, now - QUOTA_WINDOW)
    if window.n >= limit:
        wait = (window.oldest + QUOTA_WINDOW - now).total_seconds()
        raise AppError(
            ErrorCode.PUBLICATION_LIMIT, 429, headers={"Retry-After": str(max(1, math.ceil(wait)))}
        )


async def put_online(
    db: AsyncSession,
    *,
    seller_id: UUID,
    listing_id: UUID,
    event: ListingEvent,
    clock: Clock,
) -> ListingOut:
    """A transition to the shop window made by the seller, with its checks in order: 404 not
    theirs, 403 `publish_forbidden` (Q1), 409 `invalid_transition`, 422 `photo_required`, 429
    `publication_limit`. Online from now for `listings.expiry_days` (Q15)."""
    await repository.lock_seller_listings(db, seller_id)
    locked = await repository.lock_own_listing(db, listing_id=listing_id, seller_id=seller_id)
    if locked is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if not await policies.can_publish_listing(db, seller_id, clock=clock):
        raise AppError(ErrorCode.PUBLISH_FORBIDDEN, 403)
    # Checked here too, so a listing that cannot go online says 409 before anything else.
    if (ListingStatus(locked.status), event) not in TRANSITIONS:
        raise AppError(ErrorCode.INVALID_TRANSITION, 409)
    if not await repository.has_ready_photo(db, listing_id):
        raise AppError(ErrorCode.PHOTO_REQUIRED, 422)
    await check_publication_quota(db, seller_id, clock=clock)
    now = clock.now()
    # One instant for the history and the listing: `published_at` is the transition's time.
    await apply_transition(
        db,
        listing_id=listing_id,
        event=event,
        actor=Actor("user", seller_id),
        clock=FixedClock(now),
    )
    days = await repository.setting_int(db, "listings.expiry_days")
    await repository.mark_online(db, listing_id, now=now, expires_at=now + timedelta(days=days))
    return await own_listing(db, seller_id=seller_id, listing_id=listing_id)


async def publish(
    db: AsyncSession,
    *,
    seller_id: UUID,
    listing_id: UUID,
    gate: ModerationGate,
    clock: Clock,
) -> ListingOut:
    """A draft goes online, or to moderation when the gate says so."""
    event = await gate.route(db, listing_id)
    return await put_online(
        db, seller_id=seller_id, listing_id=listing_id, event=event, clock=clock
    )


# Putting back online (`renew`): the event depends on how the listing left the shop window.
_BACK_ONLINE = {
    ListingStatus.EXPIRED: ListingEvent.RENEW,
    ListingStatus.WITHDRAWN: ListingEvent.REPUBLISH,
}


async def renew(db: AsyncSession, *, seller_id: UUID, listing_id: UUID, clock: Clock) -> ListingOut:
    """An expired listing renewed, a withdrawn one republished: back online for
    `listings.expiry_days` under the publication's rules; 409 from any other status."""
    await repository.lock_seller_listings(db, seller_id)
    locked = await repository.lock_own_listing(db, listing_id=listing_id, seller_id=seller_id)
    if locked is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    event = _BACK_ONLINE.get(ListingStatus(locked.status))
    if event is None:
        raise AppError(ErrorCode.INVALID_TRANSITION, 409)
    return await put_online(
        db, seller_id=seller_id, listing_id=listing_id, event=event, clock=clock
    )


async def withdraw(
    db: AsyncSession, *, seller_id: UUID, listing_id: UUID, clock: Clock
) -> ListingOut:
    """The seller takes an active listing down, whatever the state of their account."""
    await repository.lock_seller_listings(db, seller_id)
    if await repository.lock_own_listing(db, listing_id=listing_id, seller_id=seller_id) is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    await apply_transition(
        db,
        listing_id=listing_id,
        event=ListingEvent.WITHDRAW,
        actor=Actor("user", seller_id),
        clock=clock,
    )
    return await own_listing(db, seller_id=seller_id, listing_id=listing_id)
