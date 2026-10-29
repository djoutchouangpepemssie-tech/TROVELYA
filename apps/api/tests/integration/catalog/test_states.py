"""Applying a transition of the listing state machine (section 9, P2-T04a): the status
changes, the transition is written in `listing_status_history` with its actor and reason, and a
domain event leaves through the outbox — all in the caller's transaction, or nothing."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.catalog.test_listing_gdpr import (
    _listing,  # pyright: ignore[reportPrivateUsage]
    category,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.identity.test_profile import make_account
from trovelya.core.errors import AppError
from trovelya.modules.catalog.models import ListingStatus
from trovelya.modules.catalog.service.states import SYSTEM, Actor, apply_transition
from trovelya.modules.catalog.state_machine import TRANSITIONS, ListingEvent
from trovelya.shared.clock import FixedClock, SystemClock
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]

# Plan Q25: named by their effect on the shop window.
EXPECTED_TYPES = {
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
AT = datetime(2030, 1, 1, 12, tzinfo=UTC)  # far from now: the history's time is the clock's


async def _set_status(sessionmaker: Session, listing_id: UUID, status: ListingStatus) -> None:
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = CAST(:s AS listing_status) WHERE id = :l"),
            {"s": status.value, "l": listing_id},
        )
        await db.commit()


async def _history(sessionmaker: Session, listing_id: UUID) -> list[Any]:
    """The transitions made here: the test listing comes with a row for its creation."""
    async with sessionmaker() as db:
        return list(
            (
                await db.execute(
                    text(
                        "SELECT from_status::text AS from_status, to_status::text AS to_status,"
                        " event, actor_id, actor_kind, reason_code, reason_text, created_at"
                        " FROM listing_status_history WHERE listing_id = :l AND event <> 'create'"
                        " ORDER BY id"
                    ),
                    {"l": listing_id},
                )
            ).all()
        )


async def _events(sessionmaker: Session, listing_id: UUID) -> list[Any]:
    async with sessionmaker() as db:
        return list(
            (
                await db.execute(
                    text(
                        "SELECT type, aggregate_type, payload FROM outbox_events"
                        " WHERE aggregate_id = :l ORDER BY id"
                    ),
                    {"l": listing_id},
                )
            ).all()
        )


async def _status(sessionmaker: Session, listing_id: UUID) -> str:
    async with sessionmaker() as db:
        return str(
            await db.scalar(
                text("SELECT status::text FROM listings WHERE id = :l"), {"l": listing_id}
            )
        )


@pytest.mark.parametrize(("start", "event"), list(TRANSITIONS))
async def test_each_transition_writes_history_and_event(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
    start: ListingStatus,
    event: ListingEvent,
) -> None:
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    await _set_status(sessionmaker, listing_id, start)
    actor = Actor("user", member.id)
    async with sessionmaker() as db:
        version = await db.scalar(
            text("SELECT version FROM listings WHERE id = :l"), {"l": listing_id}
        )
        moved = await apply_transition(
            db,
            listing_id=listing_id,
            event=event,
            actor=actor,
            clock=FixedClock(AT),
            reason_code="test_reason",
            reason_text="Motif lisible",
        )
        await db.commit()
    to = TRANSITIONS[(start, event)]
    assert (moved.from_status, moved.to_status) == (start, to)
    assert await _status(sessionmaker, listing_id) == to.value
    async with sessionmaker() as db:
        after = await db.scalar(
            text("SELECT version FROM listings WHERE id = :l"), {"l": listing_id}
        )
    assert after == version + 1  # If-Match: a client on the old status is stale
    [row] = await _history(sessionmaker, listing_id)
    assert (row.from_status, row.to_status, row.event) == (start.value, to.value, event.value)
    assert (row.actor_id, row.actor_kind) == (member.id, "user")
    assert (row.reason_code, row.reason_text, row.created_at) == (
        "test_reason",
        "Motif lisible",
        AT,
    )
    [outbox] = await _events(sessionmaker, listing_id)
    assert (outbox.aggregate_type, outbox.type) == ("listing", EXPECTED_TYPES[event])
    assert outbox.payload == {
        "event": event.value,
        "from": start.value,
        "to": to.value,
        "seller_id": str(member.id),
        "actor_kind": "user",
        "reason_code": "test_reason",
        "v": 1,
    }


async def test_system_transitions_named_as_the_spec(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """Section 5.6 names `listing.published`, `listing.withdrawn` and `listing.sold`; a
    transition by the platform has no actor."""
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    for event in (ListingEvent.PUBLISH, ListingEvent.WITHDRAW):
        async with sessionmaker() as db:
            await apply_transition(
                db, listing_id=listing_id, event=event, actor=SYSTEM, clock=SystemClock()
            )
            await db.commit()
    await _set_status(sessionmaker, listing_id, ListingStatus.RESERVED)
    async with sessionmaker() as db:
        await apply_transition(
            db, listing_id=listing_id, event=ListingEvent.SELL, actor=SYSTEM, clock=SystemClock()
        )
        await db.commit()
    types = [e.type for e in await _events(sessionmaker, listing_id)]
    assert types == ["listing.published", "listing.withdrawn", "listing.sold"]
    assert [r.actor_kind for r in await _history(sessionmaker, listing_id)] == ["system"] * 3


async def test_invalid_transition_409_and_nothing_written(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    await _set_status(sessionmaker, listing_id, ListingStatus.SOLD)
    async with sessionmaker() as db:
        with pytest.raises(AppError) as refused:
            await apply_transition(
                db,
                listing_id=listing_id,
                event=ListingEvent.REPUBLISH,
                actor=Actor("user", member.id),
                clock=SystemClock(),
            )
        await db.commit()  # what a route does once the error is its answer
    assert (refused.value.status, refused.value.code) == (409, "invalid_transition")
    assert await _history(sessionmaker, listing_id) == []
    assert await _events(sessionmaker, listing_id) == []


async def test_unknown_or_deleted_listing_404(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET deleted_at = now() WHERE id = :l"), {"l": listing_id}
        )
        await db.commit()
    for target in (listing_id, new_id()):
        async with sessionmaker() as db:
            with pytest.raises(AppError) as missing:
                await apply_transition(
                    db,
                    listing_id=target,
                    event=ListingEvent.PUBLISH,
                    actor=SYSTEM,
                    clock=SystemClock(),
                )
        assert missing.value.status == 404


def test_actor_kind_and_id_go_together() -> None:
    """The history's own check: a system transition has no actor, any other has one."""
    with pytest.raises(ValueError):
        Actor("system", new_id())
    with pytest.raises(ValueError):
        Actor("user")


async def test_concurrent_transitions_single_winner(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """Two withdrawals at once: the row lock lets one through; the other, finding the listing
    already withdrawn, is refused."""
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    await _set_status(sessionmaker, listing_id, ListingStatus.ACTIVE)

    async def withdraw() -> int:
        async with sessionmaker() as db:
            try:
                await apply_transition(
                    db,
                    listing_id=listing_id,
                    event=ListingEvent.WITHDRAW,
                    actor=Actor("user", member.id),
                    clock=SystemClock(),
                )
            except AppError as exc:
                return exc.status
            await asyncio.sleep(0.2)  # hold the lock while the other one waits
            await db.commit()
            return 200

    assert sorted(await asyncio.gather(withdraw(), withdraw())) == [200, 409]
    assert len(await _history(sessionmaker, listing_id)) == 1
