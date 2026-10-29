"""Putting a listing online (P2-T04b, plan Q1, Q14, Q15, Q24). Never commits.

The seller's lock comes first, as for drafts: one write of a seller's listings at a time, so
two publications cannot both slip under the quota, and the photos are never taken in two
orders (no deadlock). Checks run in this order: 404 not theirs, 403 `publish_forbidden` with
its reason (Q1), 409 `invalid_transition`, 422 `photo_required`, 429 `publication_limit`; the
moderation decides last, on a listing that may go online (P2-T05b, Q32: every putting online,
first or not): online at once, to review (`submit_for_review`), or refused (`submit_for_review`
then `reject` by the platform, the reason in the history).
"""

import math
from collections.abc import Callable, Collection
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode, FieldError
from trovelya.modules.catalog import policies, repository
from trovelya.modules.catalog.models import ListingStatus
from trovelya.modules.catalog.schemas import (
    ListingOut,
    ModerationOut,
    ModerationReason,
    PublishedOut,
)
from trovelya.modules.catalog.service.listings import own_listing
from trovelya.modules.catalog.service.moderation import Moderated, label
from trovelya.modules.catalog.service.states import SYSTEM, Actor, apply_transition
from trovelya.modules.catalog.state_machine import ListingEvent
from trovelya.shared.clock import Clock, FixedClock

QUOTA_WINDOW = timedelta(hours=24)

_REFUSALS = {
    "profile_incomplete": "Profil à compléter",
    "too_young": "Il faut avoir 18 ans pour publier",
    "account_restricted": "Ce compte ne peut pas publier pour l'instant",
}


class ModerationGate(Protocol):
    """Whether a listing goes online, to review or is refused (service/moderation.py)."""

    async def moderate(
        self, db: AsyncSession, *, listing_id: UUID, seller_id: UUID, clock: Clock
    ) -> Moderated: ...


def retry_after(put_online: list[datetime], limit: int, now: datetime) -> int | None:
    """Q24: None while fewer than `limit` puttings online fall in the last 24 hours; else the
    seconds until enough of them leave the window for one more (the whole window when the
    limit is 0: publications frozen)."""
    if limit <= 0:
        return int(QUOTA_WINDOW.total_seconds())
    if len(put_online) < limit:
        return None
    leaving = put_online[len(put_online) - limit]  # the oldest that must leave
    return max(1, math.ceil((leaving + QUOTA_WINDOW - now).total_seconds()))


async def check_publication_quota(db: AsyncSession, seller_id: UUID, *, clock: Clock) -> None:
    """429 `publication_limit` once the seller has put `listings.max_publications_per_day`
    listings online over the last 24 hours, `Retry-After` set (Q24)."""
    now = clock.now()
    limit = await repository.setting_int(db, "listings.max_publications_per_day")
    window = await repository.put_online_since(db, seller_id, now - QUOTA_WINDOW)
    wait = retry_after(window, limit, now)
    if wait is not None:
        raise AppError(ErrorCode.PUBLICATION_LIMIT, 429, headers={"Retry-After": str(wait)})


async def _put_online(
    db: AsyncSession,
    *,
    seller_id: UUID,
    listing_id: UUID,
    allowed: Collection[ListingStatus],
    online_event: Callable[[ListingStatus], ListingEvent],
    gate: ModerationGate,
    clock: Clock,
) -> PublishedOut:
    await repository.lock_seller_listings(db, seller_id)
    locked = await repository.lock_own_listing(db, listing_id=listing_id, seller_id=seller_id)
    if locked is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    refusal = await policies.publish_refusal(db, seller_id, clock=clock)
    if refusal is not None:
        raise AppError(
            ErrorCode.PUBLISH_FORBIDDEN,
            403,
            errors=[FieldError(field="account", code=refusal, message=_REFUSALS[refusal])],
        )
    status = ListingStatus(locked.status)
    if status not in allowed:
        raise AppError(ErrorCode.INVALID_TRANSITION, 409)
    if not await repository.has_ready_photo(db, listing_id):
        raise AppError(ErrorCode.PHOTO_REQUIRED, 422)
    await check_publication_quota(db, seller_id, clock=clock)
    days = await repository.setting_int(db, "listings.expiry_days")
    now = FixedClock(clock.now())  # one instant for the moderation and the transitions
    moderated = await gate.moderate(db, listing_id=listing_id, seller_id=seller_id, clock=now)
    verdict = moderated.verdict
    seller = Actor("user", seller_id)
    if verdict.outcome == "online":
        await apply_transition(
            db,
            listing_id=listing_id,
            event=online_event(status),
            actor=seller,
            clock=now,
            online_until=now.now() + timedelta(days=days),
        )
    else:  # to review, and refused by the platform at once when the item is prohibited
        steps = [(ListingEvent.SUBMIT_FOR_REVIEW, seller)]
        if verdict.outcome == "refused":
            steps.append((ListingEvent.REJECT, SYSTEM))
        for event, actor in steps:
            await apply_transition(
                db,
                listing_id=listing_id,
                event=event,
                actor=actor,
                clock=now,
                reason_code=verdict.reasons[0],
                # Every reason, for the statement of reasons (DSA art. 17).
                reason_text=", ".join(label(c) for c in verdict.reasons),
            )
    listing = await own_listing(db, seller_id=seller_id, listing_id=listing_id)
    return PublishedOut(
        **listing.model_dump(),
        moderation=ModerationOut(
            outcome=verdict.outcome,
            reasons=[ModerationReason(code=c, label=label(c)) for c in verdict.reasons],
            notice=moderated.notice,
        ),
    )


async def publish(
    db: AsyncSession,
    *,
    seller_id: UUID,
    listing_id: UUID,
    gate: ModerationGate,
    clock: Clock,
) -> PublishedOut:
    """A draft goes online, to review or is refused, as the moderation decides."""
    return await _put_online(
        db,
        seller_id=seller_id,
        listing_id=listing_id,
        allowed={ListingStatus.DRAFT},
        online_event=lambda _: ListingEvent.PUBLISH,
        gate=gate,
        clock=clock,
    )


# Putting back online (`renew`): the event depends on how the listing left the shop window.
_BACK_ONLINE = {
    ListingStatus.EXPIRED: ListingEvent.RENEW,
    ListingStatus.WITHDRAWN: ListingEvent.REPUBLISH,
}


async def renew(
    db: AsyncSession, *, seller_id: UUID, listing_id: UUID, gate: ModerationGate, clock: Clock
) -> PublishedOut:
    """An expired listing renewed, a withdrawn one republished: back online for
    `listings.expiry_days` under the publication's rules and moderation (Q32); 409 from any
    other status."""
    return await _put_online(
        db,
        seller_id=seller_id,
        listing_id=listing_id,
        allowed=_BACK_ONLINE.keys(),
        online_event=_BACK_ONLINE.__getitem__,
        gate=gate,
        clock=clock,
    )


async def withdraw(
    db: AsyncSession, *, seller_id: UUID, listing_id: UUID, clock: Clock
) -> ListingOut:
    """The seller takes an active listing down, or one awaiting moderation (Q29), whatever
    the state of their account."""
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
