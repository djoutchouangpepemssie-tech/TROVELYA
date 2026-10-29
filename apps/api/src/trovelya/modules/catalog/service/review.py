"""The staff's decisions on listings (P2-T05c1, 8.17, plan Q6, Q16, E9). Never commits.

Approving puts a listing online; rejecting or removing one takes a reason from a closed list,
its photos quarantined for the appeal (Q40). Each decision is a transition and
an audit line in one transaction; nobody decides on a listing of their own."""

from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode, FieldError
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.models import ListingStatus
from trovelya.modules.catalog.service.moderation import PROHIBITED, label
from trovelya.modules.catalog.service.states import Actor, apply_transition
from trovelya.modules.catalog.state_machine import ListingEvent
from trovelya.modules.circumvention.service import detections_of
from trovelya.modules.media.service import listing_photos
from trovelya.shared.audit import record_audit
from trovelya.shared.clock import Clock, FixedClock

# The closed list of a removal's reasons: the motives of 8.17, what the photos showed, and
# a misleading or spam listing; `other` needs its explanation.
OTHER = "other"
_IMAGES = ("image_nudity", "image_violence", "image_weapons", "image_drugs", "duplicate_image")
STAFF_REASONS = {
    **PROHIBITED.labels,
    **{code: label(code) for code in _IMAGES},
    "misleading": "Annonce trompeuse",
    "spam": "Annonce en double ou abusive",
    OTHER: "Autre motif",
}


def check_reason(reason_code: str | None, reason_text: str | None) -> None:
    """422 `validation_error` for a reason off the list, or `other` without its explanation."""
    error = None
    if reason_code not in STAFF_REASONS:
        error = FieldError(field="reason_code", code="unknown_reason", message="Motif inconnu")
    elif reason_code == OTHER and not (reason_text or "").strip():
        error = FieldError(field="reason_text", code="required", message="Préciser le motif")
    if error is not None:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, errors=[error])


async def queue(db: AsyncSession, *, public_url: str | None, limit: int) -> list[dict[str, Any]]:
    rows = await repository.review_queue(db, limit=limit)
    photos = await listing_photos.photo_variants_by_id(
        db, [m for row in rows for m in row["media_ids"]], public_url=public_url
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        reason = row["reason_code"]
        items.append(
            {
                **{k: row[k] for k in ("id", "short_id", "title", "description", "category")},
                **{k: row[k] for k in ("seller_id", "submitted_at", "reason_text")},
                "price": {"amount_minor": row["price_minor"], "currency": row["currency"]},
                "reasons": [{"code": reason, "label": label(reason)}] if reason else [],
                "photos": [photos[m] for m in row["media_ids"] if m in photos],
                "detections": await detections_of(db, source_type="listing", source_id=row["id"]),
            }
        )
    return items


async def _decide(
    db: AsyncSession,
    *,
    listing_id: UUID,
    staff_id: UUID,
    event: ListingEvent,
    action: str,
    clock: Clock,
    reason_code: str | None = None,
    reason_text: str | None = None,
) -> ListingStatus:
    locked = await repository.lock_listing_status(db, listing_id)
    if locked is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if locked.seller_id == staff_id:
        raise AppError(ErrorCode.FORBIDDEN, 403)
    now = FixedClock(clock.now())
    online_until = None
    if event is ListingEvent.APPROVE:
        days = await repository.setting_int(db, "listings.expiry_days")
        online_until = now.now() + timedelta(days=days)
    transition = await apply_transition(
        db,
        listing_id=listing_id,
        event=event,
        actor=Actor("staff", staff_id),
        clock=now,
        reason_code=reason_code,
        reason_text=reason_text,
        online_until=online_until,
    )
    if transition.to_status is ListingStatus.REMOVED:
        await quarantine_listing_photos(db, listing_id, clock=now)
    await record_audit(
        db,
        actor_type="staff",
        actor_id=staff_id,
        action=action,
        target_type="listing",
        target_id=str(listing_id),
        reason=reason_code,
        before={"status": transition.from_status.value},
        after={"status": transition.to_status.value},
    )
    return transition.to_status


async def quarantine_listing_photos(db: AsyncSession, listing_id: UUID, *, clock: Clock) -> None:
    """Q40: the photos of a listing removed by the moderation leave the public bucket, a
    private copy kept for the appeal."""
    media_ids = await repository.listing_media_ids(db, listing_id)
    await listing_photos.quarantine_photos(db, media_ids, now=clock.now())


async def approve(db: AsyncSession, *, listing_id: UUID, staff_id: UUID, clock: Clock) -> str:
    status = await _decide(
        db,
        listing_id=listing_id,
        staff_id=staff_id,
        event=ListingEvent.APPROVE,
        action="listing.approve",
        clock=clock,
    )
    return status.value


async def reject(
    db: AsyncSession,
    *,
    listing_id: UUID,
    staff_id: UUID,
    reason_code: str | None,
    reason_text: str | None,
    clock: Clock,
    remove: bool = False,
) -> str:
    """Rejects a listing awaiting review, or with `remove` takes down an active one."""
    check_reason(reason_code, reason_text)
    status = await _decide(
        db,
        listing_id=listing_id,
        staff_id=staff_id,
        event=ListingEvent.REMOVE if remove else ListingEvent.REJECT,
        action="listing.remove" if remove else "listing.reject",
        clock=clock,
        reason_code=reason_code,
        reason_text=(reason_text or "").strip() or None,
    )
    return status.value
