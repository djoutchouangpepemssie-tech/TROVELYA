"""Applying a transition of the listing state machine (section 9, plan E8): the listing is
locked, the table decides, the status changes, the transition joins `listing_status_history`
with its actor and reason, and a domain event leaves through the outbox (section 5.6). All in
the caller's transaction: a rolled-back transition leaves no trace. Never commits."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.models import ListingStatus
from trovelya.modules.catalog.state_machine import InvalidTransition, ListingEvent, next_status
from trovelya.shared.clock import Clock
from trovelya.shared.events import emit_event
from trovelya.shared.ids import new_id

# Named by their effect (plan Q25, section 5.6): what the consumers act on is whether the
# listing enters or leaves the shop window. The payload says which transition it was.
EVENT_TYPES: dict[ListingEvent, str] = {
    ListingEvent.PUBLISH: "listing.published",
    ListingEvent.APPROVE: "listing.published",
    ListingEvent.REPUBLISH: "listing.published",
    ListingEvent.RENEW: "listing.published",
    ListingEvent.APPEAL_ACCEPTED: "listing.published",
    ListingEvent.RELEASE: "listing.published",
    ListingEvent.WITHDRAW: "listing.withdrawn",
    ListingEvent.REMOVE: "listing.withdrawn",
    ListingEvent.REJECT: "listing.withdrawn",
    ListingEvent.EXPIRE: "listing.withdrawn",
    ListingEvent.SELL: "listing.sold",
    ListingEvent.SUBMIT_FOR_REVIEW: "listing.submitted_for_review",
    ListingEvent.RESERVE: "listing.reserved",
}

ActorKind = Literal["user", "staff", "system"]


@dataclass(frozen=True, slots=True)
class Actor:
    """Who made the transition: a member, a staff account, or the platform (no id)."""

    kind: ActorKind
    id: UUID | None = None

    def __post_init__(self) -> None:
        if (self.kind == "system") != (self.id is None):
            raise ValueError("a system transition has no actor id; any other has one")


SYSTEM = Actor("system")


@dataclass(frozen=True, slots=True)
class Transition:
    """The statuses before and after; the listing's `version` moved with its status."""

    from_status: ListingStatus
    to_status: ListingStatus


async def apply_transition(
    db: AsyncSession,
    *,
    listing_id: UUID,
    event: ListingEvent,
    actor: Actor,
    clock: Clock,
    reason_code: str | None = None,
    reason_text: str | None = None,
    online_until: datetime | None = None,
) -> Transition:
    """404 for a listing that does not exist or was deleted; 409 `invalid_transition` when
    the table does not allow `event` from the listing's status (nothing is written).

    Who may do it is the caller's business: this never checks that `actor` owns the listing.
    A seller's route takes `lock_seller_listings` then `lock_own_listing` first (the order of
    the drafts, so a publication and an edit never deadlock); a staff decision writes the audit
    log in the same transaction (E8). `reason_code` and `reason_text` come from the code or a
    validated staff form: the history's checks reject anything else. `online_until`: the
    listing goes online now until then (`published_at`, `expires_at`, Q15)."""
    current = await repository.lock_listing_status(db, listing_id)
    if current is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    from_status = ListingStatus(current.status)
    try:
        to_status = next_status(from_status, event)
    except InvalidTransition as exc:
        raise AppError(ErrorCode.INVALID_TRANSITION, 409) from exc
    now = clock.now()
    await repository.set_listing_status(
        db, listing_id, to_status, now=now, online_until=online_until
    )
    await repository.record_transition(
        db,
        {
            "id": new_id(),
            "listing_id": listing_id,
            "from_status": from_status.value,
            "to_status": to_status.value,
            "event": event.value,
            "actor_id": actor.id,
            "actor_kind": actor.kind,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "created_at": now,
        },
    )
    await emit_event(
        db,
        type=EVENT_TYPES[event],
        aggregate_type="listing",
        aggregate_id=listing_id,
        payload={
            "event": event.value,
            "from": from_status.value,
            "to": to_status.value,
            "seller_id": str(current.seller_id),
            "actor_kind": actor.kind,
            "reason_code": reason_code,
        },
    )
    return Transition(from_status, to_status)
