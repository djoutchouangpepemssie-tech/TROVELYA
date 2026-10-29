"""`POST /v1/listings/{id}/publish`: a draft goes online (P2-T04b, plan Q1, Q14, Q15, Q24).

Who may publish (Q1): a completed profile, 18 or over by rule E14, no erasure in progress. At
least one ready photo (Q14). At most 50 listings put online by a seller over a sliding 24
hours, every putting online counted (Q24). Online for 120 days (Q15). Moderation decides
between `active` and `pending_review` from P2-T05b; until then, always `active`.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from httpx import AsyncClient, Response
from sqlalchemy import text

from tests.integration.catalog.test_drafts import Session, create, draft, seller
from tests.integration.identity.test_profile import Account, make_account
from trovelya.modules.identity.service.profile import current_year
from trovelya.shared.clock import SystemClock
from trovelya.shared.ids import new_id


async def _draft(client: AsyncClient, sessionmaker: Session) -> tuple[Account, dict[str, Any]]:
    account, zone, media = await seller(sessionmaker)
    response = await create(client, account, draft(zone, [media]))
    assert response.status_code == 201, response.text
    return account, response.json()


async def _publish(client: AsyncClient, account: Account | None, listing_id: str) -> Response:
    return await client.post(
        f"/v1/listings/{listing_id}/publish", headers=account.headers if account else {}
    )


async def _execute(sessionmaker: Session, sql: str, **params: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def _now(sessionmaker: Session) -> datetime:
    async with sessionmaker() as db:
        now: datetime = await db.scalar(text("SELECT now()"))
    return now


async def test_draft_published_for_120_days(client: AsyncClient, sessionmaker: Session) -> None:
    account, listing = await _draft(client, sessionmaker)
    before = await _now(sessionmaker)
    response = await _publish(client, account, listing["id"])
    assert response.status_code == 200, response.text
    published = response.json()
    assert published["status"] == "active"
    at = datetime.fromisoformat(published["published_at"])
    assert before <= at <= await _now(sessionmaker)
    assert datetime.fromisoformat(published["expires_at"]) == at + timedelta(days=120)
    async with sessionmaker() as db:
        row = (
            await db.execute(
                text(
                    "SELECT h.event, h.actor_id, h.created_at, o.type FROM listing_status_history h"
                    " JOIN outbox_events o ON o.aggregate_id = h.listing_id"
                    " WHERE h.listing_id = :l AND h.event = 'publish'"
                ),
                {"l": listing["id"]},
            )
        ).one()
    assert (row.actor_id, row.created_at, row.type) == (account.id, at, "listing.published")


async def test_published_twice_409(client: AsyncClient, sessionmaker: Session) -> None:
    account, listing = await _draft(client, sessionmaker)
    assert (await _publish(client, account, listing["id"])).status_code == 200
    again = await _publish(client, account, listing["id"])
    assert (again.status_code, again.json()["code"]) == (409, "invalid_transition")


async def test_other_members_listing_404(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _draft(client, sessionmaker)
    intruder = await make_account(sessionmaker, completed=True)
    assert (await _publish(client, intruder, listing["id"])).status_code == 404
    assert (await _publish(client, intruder, str(new_id()))).status_code == 404
    assert (await _publish(client, None, listing["id"])).status_code == 401


async def test_publish_requires_completed_profile(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, listing = await _draft(client, sessionmaker)
    await _execute(
        sessionmaker, "UPDATE users SET profile_completed_at = NULL WHERE id = :u", u=account.id
    )
    response = await _publish(client, account, listing["id"])
    assert (response.status_code, response.json()["code"]) == (403, "profile_incomplete")


async def test_publish_requires_adult(client: AsyncClient, sessionmaker: Session) -> None:
    """Rule E14: born in year Y, one is taken to be (this year - Y - 1). Born 18 years before
    this year is 17: refused; 19 years before is 18: accepted."""
    account, listing = await _draft(client, sessionmaker)
    year = current_year(SystemClock())
    await _execute(
        sessionmaker, "UPDATE users SET birth_year = :y WHERE id = :u", y=year - 18, u=account.id
    )
    response = await _publish(client, account, listing["id"])
    assert (response.status_code, response.json()["code"]) == (403, "publish_forbidden")
    await _execute(
        sessionmaker, "UPDATE users SET birth_year = :y WHERE id = :u", y=year - 19, u=account.id
    )
    assert (await _publish(client, account, listing["id"])).status_code == 200


async def test_publish_refused_during_erasure_grace(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, listing = await _draft(client, sessionmaker)
    await _execute(
        sessionmaker, "UPDATE users SET erasure_requested_at = now() WHERE id = :u", u=account.id
    )
    response = await _publish(client, account, listing["id"])
    assert (response.status_code, response.json()["code"]) == (403, "publish_forbidden")


async def test_publish_requires_ready_photo(client: AsyncClient, sessionmaker: Session) -> None:
    """Its only photo removed by moderation meanwhile: nothing to show, 422."""
    account, listing = await _draft(client, sessionmaker)
    await _execute(
        sessionmaker,
        "UPDATE media SET deleted_at = now() WHERE id = :m",
        m=listing["media_ids"][0],
    )
    response = await _publish(client, account, listing["id"])
    assert (response.status_code, response.json()["code"]) == (422, "photo_required")
    async with sessionmaker() as db:
        status = await db.scalar(
            text("SELECT status::text FROM listings WHERE id = :l"), {"l": listing["id"]}
        )
    assert status == "draft"


async def _put_online(sessionmaker: Session, seller_id: UUID, *, ago: timedelta, n: int) -> None:
    """`n` puttings online by the seller `ago`, of every kind Q24 counts, on a listing of
    theirs (written straight into the history: 50 real listings would be slow)."""
    async with sessionmaker() as db:
        listing_id = await db.scalar(
            text("SELECT id FROM listings WHERE seller_id = :s LIMIT 1"), {"s": seller_id}
        )
        events = ["publish", "submit_for_review", "republish", "renew"]
        for i in range(n):
            await db.execute(
                text(
                    "INSERT INTO listing_status_history (id, listing_id, from_status, to_status,"
                    " event, actor_id, actor_kind, created_at)"
                    " VALUES (:id, :l, 'draft', 'active', :e, :s, 'user', now() - CAST(:ago AS interval))"
                ),
                {"id": new_id(), "l": listing_id, "e": events[i % 4], "s": seller_id}
                | {"ago": ago},
            )
        await db.commit()


async def test_publication_limit_50_over_24_hours(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, listing = await _draft(client, sessionmaker)
    await _put_online(sessionmaker, account.id, ago=timedelta(hours=23), n=50)
    await _put_online(sessionmaker, account.id, ago=timedelta(hours=25), n=10)  # out of window
    refused = await _publish(client, account, listing["id"])
    assert (refused.status_code, refused.json()["code"]) == (429, "publication_limit")
    # The oldest of the window leaves it in an hour.
    assert 3500 <= int(refused.headers["retry-after"]) <= 3601
    await _execute(
        sessionmaker,
        "UPDATE listing_status_history SET created_at = created_at - interval '2 hours'"
        " WHERE actor_id = :s AND created_at > now() - interval '24 hours'",
        s=account.id,
    )
    assert (await _publish(client, account, listing["id"])).status_code == 200


async def test_staff_and_system_transitions_not_counted(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """Only what the seller put online counts: a moderator's approval is not theirs."""
    account, listing = await _draft(client, sessionmaker)
    await _put_online(sessionmaker, account.id, ago=timedelta(hours=1), n=49)
    await _execute(
        sessionmaker,
        "INSERT INTO listing_status_history (id, listing_id, from_status, to_status, event,"
        " actor_kind) VALUES (:id, :l, 'expired', 'active', 'renew', 'system')",
        id=new_id(),
        l=listing["id"],
    )
    assert (await _publish(client, account, listing["id"])).status_code == 200


async def test_concurrent_publish_single_transition(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, listing = await _draft(client, sessionmaker)
    responses = await asyncio.gather(
        _publish(client, account, listing["id"]), _publish(client, account, listing["id"])
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    async with sessionmaker() as db:
        published = await db.scalar(
            text(
                "SELECT count(*) FROM listing_status_history WHERE listing_id = :l"
                " AND event = 'publish'"
            ),
            {"l": listing["id"]},
        )
    assert published == 1
