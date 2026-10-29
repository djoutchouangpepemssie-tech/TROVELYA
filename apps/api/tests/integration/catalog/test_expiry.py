"""The daily expiry of listings (P2-T04d, section 9.1, plan Q15): an active listing whose
`expires_at` has come leaves the shop window, one transition at a time (history and
`listing.withdrawn` event), by the platform. Running it again changes nothing."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from tests.integration.catalog.test_listing_gdpr import (
    _listing,  # pyright: ignore[reportPrivateUsage]
    category,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_states import Session
from tests.integration.identity.test_profile import make_account
from trovelya.modules.catalog.service.expiry import expire_listings
from trovelya.shared.clock import FixedClock


async def _active(sessionmaker: Session, category_id: UUID, *, published: timedelta) -> UUID:
    """An active listing published `published` ago, for the 120 days of Q15."""
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category_id, "Lampe opaline verte")
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE listings SET status = 'active', published_at = now() - CAST(:ago AS interval),"
                " expires_at = now() - CAST(:ago AS interval) + interval '120 days' WHERE id = :l"
            ),
            {"ago": published, "l": listing_id},
        )
        await db.commit()
    return listing_id


async def _state(sessionmaker: Session, listing_id: UUID) -> tuple[str, list[str], list[str]]:
    async with sessionmaker() as db:
        status = await db.scalar(
            text("SELECT status::text FROM listings WHERE id = :l"), {"l": listing_id}
        )
        history = list(
            await db.scalars(
                text(
                    "SELECT event || ':' || actor_kind FROM listing_status_history"
                    " WHERE listing_id = :l AND event <> 'create' ORDER BY id"
                ),
                {"l": listing_id},
            )
        )
        events = list(
            await db.scalars(
                text("SELECT type FROM outbox_events WHERE aggregate_id = :l ORDER BY id"),
                {"l": listing_id},
            )
        )
    return str(status), history, events


async def _now(sessionmaker: Session) -> datetime:
    async with sessionmaker() as db:
        now: datetime = await db.scalar(text("SELECT now()"))
    return now


async def test_expiry_after_120_days(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    almost = await _active(sessionmaker, category, published=timedelta(days=119, hours=23))
    due = await _active(sessionmaker, category, published=timedelta(days=120, minutes=1))
    await expire_listings(sessionmaker, clock=FixedClock(await _now(sessionmaker)))
    assert await _state(sessionmaker, almost) == ("active", [], [])
    assert await _state(sessionmaker, due) == (
        "expired",
        ["expire:system"],
        ["listing.withdrawn"],
    )


async def test_expire_job_idempotent(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    due = await _active(sessionmaker, category, published=timedelta(days=200))
    clock = FixedClock(await _now(sessionmaker))
    await expire_listings(sessionmaker, clock=clock)
    await expire_listings(sessionmaker, clock=clock)
    assert await _state(sessionmaker, due) == ("expired", ["expire:system"], ["listing.withdrawn"])


async def test_only_active_listings_expire(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """A withdrawn or deleted listing past its date is left as it is."""
    withdrawn = await _active(sessionmaker, category, published=timedelta(days=200))
    deleted = await _active(sessionmaker, category, published=timedelta(days=200))
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = 'withdrawn' WHERE id = :l"), {"l": withdrawn}
        )
        await db.execute(
            text("UPDATE listings SET deleted_at = now() WHERE id = :l"), {"l": deleted}
        )
        await db.commit()
    await expire_listings(sessionmaker, clock=FixedClock(await _now(sessionmaker)))
    assert (await _state(sessionmaker, withdrawn))[0] == "withdrawn"
    assert await _state(sessionmaker, deleted) == ("active", [], [])


async def test_expiry_in_batches(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """More due listings than a batch: every one expires in the same run."""
    due = [await _active(sessionmaker, category, published=timedelta(days=130)) for _ in range(5)]
    expired = await expire_listings(
        sessionmaker, clock=FixedClock(await _now(sessionmaker)), batch=2
    )
    assert expired >= 5
    for listing_id in due:
        assert (await _state(sessionmaker, listing_id))[0] == "expired"


async def test_listing_being_changed_is_left_for_the_next_run(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """A listing locked by its seller right now is skipped, not waited for."""
    due = await _active(sessionmaker, category, published=timedelta(days=130))
    async with sessionmaker() as seller:
        await seller.execute(text("SELECT 1 FROM listings WHERE id = :l FOR UPDATE"), {"l": due})
        await expire_listings(sessionmaker, clock=FixedClock(await _now(sessionmaker)))
        await seller.rollback()
    assert (await _state(sessionmaker, due))[0] == "active"
    await expire_listings(sessionmaker, clock=FixedClock(await _now(sessionmaker)))
    assert (await _state(sessionmaker, due))[0] == "expired"
