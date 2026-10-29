"""Daily purge of ended listings (P2-T04e, plan Q19, PII.md).

Deleted by the seller: gone 30 days after `deleted_at`. Withdrawn or expired: 365 days after
that status was reached. Removed by moderation: 180 days after the removal. A listing back
online is never purged; its photos, histories and other members' favorites go with it. The
public positions (Q20) no listing of the seller stands on any more go too. Sold listings keep
a minimal record while an order points to them: their content is purged with the orders of P4.
"""

import asyncio
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text

from tests.integration.catalog.test_draft_rules import photo
from tests.integration.catalog.test_listing_gdpr import (
    _listing,  # pyright: ignore[reportPrivateUsage]
    category,  # noqa: F401  # pyright: ignore[reportUnusedImport] (fixture)
)
from tests.integration.catalog.test_states import Session
from tests.integration.identity.test_profile import make_account
from trovelya.modules.catalog.repository import erase_catalog
from trovelya.modules.catalog.service.retention import purge_ended_listings
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id


async def _now(sessionmaker: Session) -> datetime:
    async with sessionmaker() as db:
        now: datetime = await db.scalar(text("SELECT now()"))
    return now


async def _ended(sessionmaker: Session, category_id: UUID, status: str, *, ago: timedelta) -> UUID:
    """A listing that reached `status` `ago` (a transition in its history)."""
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category_id, "Lampe opaline verte")
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = CAST(:s AS listing_status) WHERE id = :l"),
            {"s": status, "l": listing_id},
        )
        await db.execute(
            text(
                "INSERT INTO listing_status_history (id, listing_id, from_status, to_status,"
                " event, actor_kind, created_at) VALUES (:id, :l, 'active',"
                " CAST(:s AS listing_status), 'test', 'system', now() - CAST(:ago AS interval))"
            ),
            {"id": new_id(), "l": listing_id, "s": status, "ago": ago},
        )
        await db.commit()
    return listing_id


async def _exists(sessionmaker: Session, listing_id: UUID) -> bool:
    async with sessionmaker() as db:
        return bool(
            await db.scalar(
                text("SELECT EXISTS (SELECT 1 FROM listings WHERE id = :l)"), {"l": listing_id}
            )
        )


async def _purge(sessionmaker: Session) -> int:
    return await purge_ended_listings(sessionmaker, clock=FixedClock(await _now(sessionmaker)))


@pytest.mark.parametrize(
    ("status", "days"), [("withdrawn", 365), ("expired", 365), ("removed", 180)]
)
async def test_ended_listing_purged_after_its_retention(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
    status: str,
    days: int,
) -> None:
    kept = await _ended(sessionmaker, category, status, ago=timedelta(days=days, hours=-1))
    gone = await _ended(sessionmaker, category, status, ago=timedelta(days=days, hours=1))
    await _purge(sessionmaker)
    assert await _exists(sessionmaker, kept)
    assert not await _exists(sessionmaker, gone)


async def test_deleted_listing_purged_after_30_days(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """Counted from the deletion, whatever the status: a deleted draft too."""
    member = await make_account(sessionmaker, completed=True)
    kept, gone = [
        await _listing(sessionmaker, member.id, category, "Lampe opaline verte") for _ in range(2)
    ]
    async with sessionmaker() as db:
        for listing_id, ago in (
            (kept, timedelta(days=29, hours=23)),
            (gone, timedelta(days=30, hours=1)),
        ):
            await db.execute(
                text(
                    "UPDATE listings SET deleted_at = now() - CAST(:ago AS interval) WHERE id = :l"
                ),
                {"ago": ago, "l": listing_id},
            )
        await db.commit()
    await _purge(sessionmaker)
    assert await _exists(sessionmaker, kept)
    assert not await _exists(sessionmaker, gone)


async def test_back_online_or_living_never_purged(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """Withdrawn long ago, then republished: the last status counts, not an old one."""
    republished = await _ended(sessionmaker, category, "withdrawn", ago=timedelta(days=400))
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = 'active' WHERE id = :l"), {"l": republished}
        )
        await db.commit()
    living = [
        await _ended(sessionmaker, category, status, ago=timedelta(days=400))
        for status in ("draft", "active", "pending_review", "reserved", "sold")
    ]
    await _purge(sessionmaker)
    for listing_id in (republished, *living):
        assert await _exists(sessionmaker, listing_id)


async def test_what_hangs_on_the_listing_goes_with_it(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    gone = await _ended(sessionmaker, category, "expired", ago=timedelta(days=400))
    fan = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        seller_id = await db.scalar(
            text("SELECT seller_id FROM listings WHERE id = :l"), {"l": gone}
        )
    media_id = await photo(sessionmaker, seller_id)
    async with sessionmaker() as db:
        await db.execute(
            text("INSERT INTO listing_media (listing_id, media_id, position) VALUES (:l, :m, 0)"),
            {"l": gone, "m": media_id},
        )
        await db.execute(
            text("INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)"),
            {"u": fan.id, "l": gone},
        )
        await db.commit()
    await _purge(sessionmaker)
    async with sessionmaker() as db:
        left = await db.scalar(
            text(
                "SELECT (SELECT count(*) FROM listing_media WHERE listing_id = :l)"
                " + (SELECT count(*) FROM favorites WHERE listing_id = :l)"
                " + (SELECT count(*) FROM listing_status_history WHERE listing_id = :l)"
                " + (SELECT count(*) FROM listing_price_history WHERE listing_id = :l)"
            ),
            {"l": gone},
        )
        # Its photo is deleted: its files leave storage at the media purge's next run.
        discarded = await db.scalar(
            text("SELECT deleted_at IS NOT NULL FROM media WHERE id = :m"), {"m": media_id}
        )
    assert left == 0
    assert discarded


async def _positions(sessionmaker: Session, seller_id: UUID) -> int:
    async with sessionmaker() as db:
        return int(
            await db.scalar(
                text("SELECT count(*) FROM listing_public_positions WHERE seller_id = :s"),
                {"s": seller_id},
            )
        )


async def _keep_position(sessionmaker: Session, seller_id: UUID, lon: float, lat: float) -> None:
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO listing_public_positions (id, seller_id, location, location_public,"
                " drawn_at) VALUES (:id, :s, ST_MakePoint(:lon, :lat)::geography,"
                " ST_MakePoint(:lon, :lat + 0.003)::geography, now())"
            ),
            {"id": new_id(), "s": seller_id, "lon": lon, "lat": lat},
        )
        await db.commit()


async def test_unused_public_positions_purged(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """A kept place is used while a listing of the seller (any status, deleted ones included,
    until purged) stands within 50 m of it (Q20, E18)."""
    member = await make_account(sessionmaker, completed=True)
    await _listing(sessionmaker, member.id, category, "Lampe opaline verte")  # at 4.84, 45.75
    await _keep_position(sessionmaker, member.id, 4.8402, 45.7501)  # about 20 m away: used
    await _keep_position(sessionmaker, member.id, 4.85, 45.75)  # about 780 m away: unused
    await _purge(sessionmaker)
    assert await _positions(sessionmaker, member.id) == 1


async def test_positions_of_a_seller_drawing_are_left_alone(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """A seller saving a draft holds the lock of their places: the purge does not wait for it
    and leaves their positions to the next run."""
    member = await make_account(sessionmaker, completed=True)
    await _keep_position(sessionmaker, member.id, 4.85, 45.75)
    async with sessionmaker() as drawing:
        await drawing.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended("
                "'trovelya.public_position:' || :s, 0))"
            ),
            {"s": str(member.id)},
        )
        await _purge(sessionmaker)
        assert await _positions(sessionmaker, member.id) == 1
        await drawing.rollback()
    await _purge(sessionmaker)
    assert await _positions(sessionmaker, member.id) == 0


async def _history_row(
    sessionmaker: Session, listing_id: UUID, status: str, ago: timedelta
) -> None:
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO listing_status_history (id, listing_id, to_status, event, actor_kind,"
                " created_at) VALUES (:id, :l, CAST(:s AS listing_status), 'test', 'system',"
                " now() - CAST(:ago AS interval))"
            ),
            {"id": new_id(), "l": listing_id, "s": status, "ago": ago},
        )
        await db.commit()


async def test_withdrawn_again_counts_from_the_last_time(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """Withdrawn 400 days ago, republished 10 days ago, withdrawn again 5 days ago: kept."""
    listing_id = await _ended(sessionmaker, category, "withdrawn", ago=timedelta(days=400))
    await _history_row(sessionmaker, listing_id, "active", timedelta(days=10))
    await _history_row(sessionmaker, listing_id, "withdrawn", timedelta(days=5))
    await _purge(sessionmaker)
    assert await _exists(sessionmaker, listing_id)


async def _delete(sessionmaker: Session, listing_id: UUID, ago: timedelta) -> None:
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET deleted_at = now() - CAST(:ago AS interval) WHERE id = :l"),
            {"ago": ago, "l": listing_id},
        )
        await db.commit()


async def test_removed_then_deleted_keeps_the_longer_retention(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """Removed by moderation, then deleted by its seller: the 180 days of a removal hold
    (DSA art. 20); a reserved or sold listing waits for the orders of P4."""
    recent = await _ended(sessionmaker, category, "removed", ago=timedelta(days=100))
    old = await _ended(sessionmaker, category, "removed", ago=timedelta(days=200))
    sold = await _ended(sessionmaker, category, "sold", ago=timedelta(days=400))
    for listing_id in (recent, old, sold):
        await _delete(sessionmaker, listing_id, timedelta(days=40))
    await _purge(sessionmaker)
    assert await _exists(sessionmaker, recent)
    assert not await _exists(sessionmaker, old)
    assert await _exists(sessionmaker, sold)


async def _brand(sessionmaker: Session, listing_id: UUID, *, origin: str) -> UUID:
    brand_id = new_id()
    async with sessionmaker() as db:
        seller_id = await db.scalar(
            text("SELECT seller_id FROM listings WHERE id = :l"), {"l": listing_id}
        )
        await db.execute(
            text(
                "INSERT INTO brands (id, name, slug, origin, created_by) VALUES (:id, :n, :s, :o,"
                " CASE WHEN :o = 'member' THEN CAST(:u AS uuid) END)"
            ),
            {
                "id": brand_id,
                "n": f"Marque {brand_id.hex[-12:]}",
                "s": f"m-{brand_id.hex[-12:]}",
                "o": origin,
                "u": seller_id,
            },
        )
        await db.execute(
            text("UPDATE listings SET brand_id = :b WHERE id = :l"),
            {"b": brand_id, "l": listing_id},
        )
        await db.commit()
    return brand_id


async def test_member_brand_goes_with_its_last_listing(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """E19, PII.md: a brand a member typed lives as long as a listing carries it."""
    gone = await _ended(sessionmaker, category, "expired", ago=timedelta(days=400))
    shared = await _ended(sessionmaker, category, "expired", ago=timedelta(days=400))
    seeded = await _ended(sessionmaker, category, "expired", ago=timedelta(days=400))
    lonely = await _brand(sessionmaker, gone, origin="member")
    kept = await _brand(sessionmaker, shared, origin="member")
    living = await _ended(sessionmaker, category, "active", ago=timedelta(days=1))
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET brand_id = :b WHERE id = :l"), {"b": kept, "l": living}
        )
        await db.commit()
    seed = await _brand(sessionmaker, seeded, origin="seed")
    await _purge(sessionmaker)
    async with sessionmaker() as db:
        left = set(
            await db.scalars(
                text("SELECT id FROM brands WHERE id = ANY(:ids)"), {"ids": [lonely, kept, seed]}
            )
        )
    assert left == {kept, seed}


async def test_price_watches_go_too(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    gone = await _ended(sessionmaker, category, "expired", ago=timedelta(days=400))
    fan = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        await db.execute(
            text("INSERT INTO price_watches (user_id, listing_id) VALUES (:u, :l)"),
            {"u": fan.id, "l": gone},
        )
        await db.commit()
    await _purge(sessionmaker)
    async with sessionmaker() as db:
        left = await db.scalar(
            text("SELECT count(*) FROM price_watches WHERE listing_id = :l"), {"l": gone}
        )
    assert left == 0


async def test_deleted_listing_still_holds_its_place(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """A deleted listing kept for its 30 days still stands on its place (Q20)."""
    member = await make_account(sessionmaker, completed=True)
    listing_id = await _listing(sessionmaker, member.id, category, "Lampe opaline verte")
    await _delete(sessionmaker, listing_id, timedelta(days=1))
    await _keep_position(sessionmaker, member.id, 4.8402, 45.7501)
    await _purge(sessionmaker)
    assert await _positions(sessionmaker, member.id) == 1


async def test_retention_of_zero_days_refused(sessionmaker: Session) -> None:
    """A broken setting stops the purge instead of erasing every ended listing at once."""
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE platform_settings SET value = '0'"
                " WHERE key = 'retention.ended_listing_days'"
            )
        )
        await db.commit()
    try:
        with pytest.raises(ValueError):
            await _purge(sessionmaker)
    finally:
        async with sessionmaker() as db:
            await db.execute(
                text(
                    "UPDATE platform_settings SET value = '365'"
                    " WHERE key = 'retention.ended_listing_days'"
                )
            )
            await db.commit()


async def test_purge_and_account_erasure_never_deadlock(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    """A member being erased has favorited a listing due for the purge: the erasure locks the
    listing first, the purge skips it and finishes; the listing goes at the next run."""
    gone = await _ended(sessionmaker, category, "expired", ago=timedelta(days=400))
    fan = await make_account(sessionmaker, completed=True)
    async with sessionmaker() as db:
        await db.execute(
            text("INSERT INTO favorites (user_id, listing_id) VALUES (:u, :l)"),
            {"u": fan.id, "l": gone},
        )
        await db.execute(text("UPDATE listings SET favorite_count = 1 WHERE id = :l"), {"l": gone})
        await db.commit()
    async with sessionmaker() as erasing:
        await erase_catalog(erasing, fan.id)
        await asyncio.wait_for(_purge(sessionmaker), timeout=10)
        await erasing.commit()
    assert await _exists(sessionmaker, gone)
    await _purge(sessionmaker)
    assert not await _exists(sessionmaker, gone)


async def test_more_than_a_batch(
    sessionmaker: Session,
    category: UUID,  # noqa: F811
) -> None:
    due = [
        await _ended(sessionmaker, category, "expired", ago=timedelta(days=400)) for _ in range(5)
    ]
    async with sessionmaker() as db:
        now = await db.scalar(text("SELECT now()"))
    await purge_ended_listings(sessionmaker, clock=FixedClock(now), batch=2)
    for listing_id in due:
        assert not await _exists(sessionmaker, listing_id)
