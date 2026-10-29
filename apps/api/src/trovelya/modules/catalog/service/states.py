"""Applying a transition of the listing state machine (section 9, plan E8): the listing is
locked, the table decides, the status changes, the transition joins `listing_status_history`
with its actor and reason, and a domain event leaves through the outbox (section 5.6). All in
the caller's transaction: a rolled-back transition leaves no trace. Never commits."""

from dataclasses import dataclass
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

# Section 5.6 names `listing.published`, `listing.withdrawn` and `listing.sold`; the others
# follow the same pattern. The payload says which transition it was.
EVENT_TYPES: dict[ListingEvent, str] = {
    ListingEvent.PUBLISH: "listing.published",
    ListingEvent.SUBMIT_FOR_REVIEW: "listing.submitted_for_review",
    ListingEvent.APPROVE: "listing.approved",
    ListingEvent.REJECT: "listing.rejected",
    ListingEvent.RESERVE: "listing.reserved",
    ListingEvent.RELEASE: "listing.released",
    ListingEvent.SELL: "listing.sold",
    ListingEvent.WITHDRAW: "listing.withdrawn",
    ListingEvent.REPUBLISH: "listing.republished",
    ListingEvent.REMOVE: "listing.removed",
    ListingEvent.APPEAL_ACCEPTED: "listing.reinstated",
    ListingEvent.EXPIRE: "listing.expired",
    ListingEvent.RENEW: "listing.renewed",
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
) -> Transition:
    """404 for a listing that does not exist or was deleted; 409 `invalid_transition` when
    the table does not allow `event` from the listing's status (nothing is written)."""
    current = await repository.lock_listing_status(db, listing_id)
    if current is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    from_status = ListingStatus(current)
    try:
        to_status = next_status(from_status, event)
    except InvalidTransition as exc:
        raise AppError(ErrorCode.INVALID_TRANSITION, 409) from exc
    await repository.set_listing_status(db, listing_id, to_status)
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
            "created_at": clock.now(),
        },
    )
    await emit_event(
        db,
        type=EVENT_TYPES[event],
        aggregate_type="listing",
        aggregate_id=listing_id,
        payload={"event": event.value, "from": from_status.value, "to": to_status.value},
    )
    return Transition(from_status, to_status)
