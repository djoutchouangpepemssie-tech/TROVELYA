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

from tests.integration.catalog.test_draft_rules import photo
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
    assert _refusal(response) == "too_young"
    await _execute(sessionmaker, "UPDATE users SET birth_year = NULL WHERE id = :u", u=account.id)
    assert _refusal(await _publish(client, account, listing["id"])) == "too_young"
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
    assert _refusal(await _publish(client, account, listing["id"])) == "account_restricted"


async def test_restricted_account_may_publish(client: AsyncClient, sessionmaker: Session) -> None:
    """`restricted` lowers the visibility of the account's listings; it is no suspension."""
    account, listing = await _draft(client, sessionmaker)
    await _execute(
        sessionmaker, "UPDATE users SET status = 'restricted' WHERE id = :u", u=account.id
    )
    assert (await _publish(client, account, listing["id"])).status_code == 200


def _refusal(response: Response) -> str:
    """The reason of a 403 `publish_forbidden` (plan P2, access answers)."""
    problem = response.json()
    assert (response.status_code, problem["code"]) == (403, "publish_forbidden")
    [reason] = problem["errors"]
    assert reason["field"] == "account"
    return str(reason["code"])


async def test_publish_requires_ready_photo(client: AsyncClient, sessionmaker: Session) -> None:
    """Its only photo back in processing, then removed by moderation: nothing to show, 422."""
    account, listing = await _draft(client, sessionmaker)
    for change in ("status = 'processing'", "status = 'ready', deleted_at = now()"):
        await _execute(
            sessionmaker,
            {
                "status = 'processing'": "UPDATE media SET status = 'processing' WHERE id = :m",
                "status = 'ready', deleted_at = now()": (
                    "UPDATE media SET status = 'ready', deleted_at = now() WHERE id = :m"
                ),
            }[change],
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
                    " VALUES (:id, :l, 'draft', 'active', :e, :s, 'user',"
                    " now() - CAST(:ago AS interval))"
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
    # The oldest of the window leaves it in about an hour (exact values: test_quota_window).
    assert 3500 <= int(refused.headers["retry-after"]) <= 3601
    await _execute(
        sessionmaker,
        "UPDATE listing_status_history SET created_at = created_at - interval '2 hours'"
        " WHERE actor_id = :s AND created_at > now() - interval '24 hours'",
        s=account.id,
    )
    assert (await _publish(client, account, listing["id"])).status_code == 200


async def test_only_puttings_online_by_the_seller_counted(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """Q24: a withdrawal is no putting online, and an approval by a moderator (even one who
    sells too) or the platform is not the seller's."""
    account, listing = await _draft(client, sessionmaker)
    await _put_online(sessionmaker, account.id, ago=timedelta(hours=1), n=49)
    for event, kind, actor in (
        ("withdraw", "user", account.id),
        ("approve", "staff", account.id),
        ("renew", "system", None),
    ):
        await _execute(
            sessionmaker,
            "INSERT INTO listing_status_history (id, listing_id, from_status, to_status, event,"
            " actor_id, actor_kind) VALUES (:id, :l, 'draft', 'active', :e, :a, :k)",
            id=new_id(),
            l=listing["id"],
            e=event,
            a=actor,
            k=kind,
        )
    assert (await _publish(client, account, listing["id"])).status_code == 200


async def test_errors_in_order(client: AsyncClient, sessionmaker: Session) -> None:
    """With the quota used up, a listing that cannot go online says why first: 409 for a
    published one, 422 for one with no ready photo; the quota is not spent on them."""
    account, listing = await _draft(client, sessionmaker)
    assert (await _publish(client, account, listing["id"])).status_code == 200
    await _put_online(sessionmaker, account.id, ago=timedelta(hours=1), n=50)
    assert (await _publish(client, account, listing["id"])).status_code == 409
    zone = listing["location"]["id"]
    media = await photo(sessionmaker, account.id)
    other = (await create(client, account, draft(zone, [media]))).json()
    await _execute(sessionmaker, "UPDATE media SET deleted_at = now() WHERE id = :m", m=media)
    assert (await _publish(client, account, other["id"])).status_code == 422


async def test_quota_held_for_two_listings_at_once(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """One put online left: two drafts published at once cannot both take it (the seller's
    lock, not only the listing's)."""
    account, first = await _draft(client, sessionmaker)
    zone = first["location"]["id"]
    second = (
        await create(client, account, draft(zone, [await photo(sessionmaker, account.id)]))
    ).json()
    await _put_online(sessionmaker, account.id, ago=timedelta(hours=1), n=49)
    responses = await asyncio.gather(
        _publish(client, account, first["id"]), _publish(client, account, second["id"])
    )
    assert sorted(r.status_code for r in responses) == [200, 429]


async def test_expiry_days_is_a_setting(client: AsyncClient, sessionmaker: Session) -> None:
    account, listing = await _draft(client, sessionmaker)
    await _execute(
        sessionmaker,
        "UPDATE platform_settings SET value = '30' WHERE key = 'listings.expiry_days'",
    )
    try:
        published = (await _publish(client, account, listing["id"])).json()
    finally:
        await _execute(
            sessionmaker,
            "UPDATE platform_settings SET value = '120' WHERE key = 'listings.expiry_days'",
        )
    at = datetime.fromisoformat(published["published_at"])
    assert datetime.fromisoformat(published["expires_at"]) == at + timedelta(days=30)
    assert published["version"] == listing["version"] + 1  # one change, one version


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
