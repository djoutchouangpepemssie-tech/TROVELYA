"""The staff's review queue (P2-T05c1, plan Q6, Q16, E9): listings awaiting moderation, oldest
first; approve puts one online, reject (closed list of reasons) or remove (`listing.remove_any`)
takes it down with its photos. Every decision is in the history and the audit log."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text

from tests.integration.catalog.test_drafts import Session, create, draft, seller
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from tests.integration.identity.test_staff_access import Staff, make_staff
from trovelya.shared.clock import FixedClock

QUEUE = "/v1/staff/moderation/listings"


async def _moderator(sessionmaker: Session, *roles: str) -> Staff:
    now = FixedClock(datetime.now(UTC))
    return await make_staff(sessionmaker, *(roles or ("staff_moderator",)), clock=now)


async def _listing(
    client: AsyncClient, sessionmaker: Session, **changes: Any
) -> tuple[Any, dict[str, Any]]:
    account, zone, media = await seller(sessionmaker)
    created = await create(client, account, draft(zone, [media], **changes))
    assert created.status_code == 201, created.text
    published = await _call(client, account, created.json()["id"], "publish")
    assert published.status_code == 200, published.text
    return account, published.json()


async def _in_review(client: AsyncClient, sessionmaker: Session) -> tuple[Any, dict[str, Any]]:
    account, listing = await _listing(
        client, sessionmaker, description="Pistolet ancien de collection, belle patine."
    )
    assert listing["status"] == "pending_review"
    return account, listing


async def _decide(
    client: AsyncClient, staff: Staff, listing_id: str, action: str, body: Any = None
) -> Response:
    return await client.post(f"{QUEUE}/{listing_id}/{action}", headers=staff.headers, json=body)


async def _audit(sessionmaker: Session, listing_id: str) -> list[tuple[Any, ...]]:
    async with sessionmaker() as db:
        rows = await db.execute(
            text(
                "SELECT actor_type, action, reason FROM audit_log"
                " WHERE target_type = 'listing' AND target_id = :l ORDER BY id"
            ),
            {"l": listing_id},
        )
        return [tuple(r) for r in rows]


async def _photos_deleted(sessionmaker: Session, listing_id: str) -> bool:
    async with sessionmaker() as db:
        return bool(
            await db.scalar(
                text(
                    "SELECT bool_and(m.deleted_at IS NOT NULL) FROM listing_media lm"
                    " JOIN media m ON m.id = lm.media_id WHERE lm.listing_id = :l"
                ),
                {"l": listing_id},
            )
        )


async def test_staff_without_the_permission_gets_403(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """A member is refused on every staff route (test_access_matrix.py); so is staff without
    `moderation.review`."""
    support = await _moderator(sessionmaker, "staff_support")
    assert (await client.get(QUEUE, headers=support.headers)).status_code == 403


async def test_queue_oldest_first_with_reasons(client: AsyncClient, sessionmaker: Session) -> None:
    _, first = await _in_review(client, sessionmaker)
    _, second = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    response = await client.get(QUEUE, headers=staff.headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = [item["id"] for item in items]
    assert ids.index(first["id"]) < ids.index(second["id"])
    item = items[ids.index(first["id"])]
    assert item["reasons"] == [{"code": "weapons", "label": "Armes et munitions"}]
    assert item["title"] == "Robe en lin bleue"
    assert len(item["photos"]) == 1
    assert {"submitted_at", "seller_id", "detections"} <= set(item)


async def test_approve_publishes_and_audits(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    response = await _decide(client, staff, listing["id"], "approve")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    page = await client.get(f"/v1/listings/{listing['id']}")
    assert page.status_code == 200  # now visible to anybody
    assert page.json()["status"] == "active"
    assert await _audit(sessionmaker, listing["id"]) == [("staff", "listing.approve", None)]
    queue = (await client.get(QUEUE, headers=staff.headers)).json()["items"]
    assert listing["id"] not in [item["id"] for item in queue]


async def test_reject_requires_a_known_reason(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    for body in (None, {}, {"reason_code": "made_up"}, {"reason_code": "other"}):
        response = await _decide(client, staff, listing["id"], "reject", body)
        assert response.status_code == 422, (body, response.text)


async def test_reject_removes_listing_and_photos(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """Q6: a listing removed by the moderation leaves storage at once (the purge's next run)."""
    _, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    response = await _decide(
        client, staff, listing["id"], "reject", {"reason_code": "weapons", "reason_text": "Arme"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "removed"
    assert await _photos_deleted(sessionmaker, listing["id"])
    async with sessionmaker() as db:
        row = (
            await db.execute(
                text(
                    "SELECT actor_kind, reason_code, reason_text FROM listing_status_history"
                    " WHERE listing_id = :l AND event = 'reject'"
                ),
                {"l": listing["id"]},
            )
        ).one()
    assert tuple(row) == ("staff", "weapons", "Arme")
    assert await _audit(sessionmaker, listing["id"]) == [("staff", "listing.reject", "weapons")]


async def test_automatic_refusal_removes_photos(client: AsyncClient, sessionmaker: Session) -> None:
    """Q6 holds for a refusal by the platform too (P2-T05b1)."""
    _, listing = await _listing(client, sessionmaker, title="Bouteille de whisky 12 ans")
    assert listing["status"] == "removed"
    assert await _photos_deleted(sessionmaker, listing["id"])


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_only_a_listing_awaiting_review(
    client: AsyncClient, sessionmaker: Session, action: str
) -> None:
    _, listing = await _listing(client, sessionmaker)  # active
    staff = await _moderator(sessionmaker)
    response = await _decide(client, staff, listing["id"], action, {"reason_code": "weapons"})
    assert (response.status_code, response.json()["code"]) == (409, "invalid_transition")


async def test_unknown_listing_404(client: AsyncClient, sessionmaker: Session) -> None:
    staff = await _moderator(sessionmaker)
    response = await _decide(client, staff, "01a18434-f2fe-740a-ba0b-58d6b5aefec2", "approve")
    assert response.status_code == 404


async def test_staff_cannot_review_own_listing(client: AsyncClient, sessionmaker: Session) -> None:
    """A staff account has no listing; were one to have one, the decision is refused."""
    _, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET seller_id = :s WHERE id = :l"),
            {"s": staff.id, "l": listing["id"]},
        )
        await db.commit()
    assert (await _decide(client, staff, listing["id"], "approve")).status_code == 403


async def test_concurrent_decisions_single_transition(
    client: AsyncClient, sessionmaker: Session
) -> None:
    _, listing = await _in_review(client, sessionmaker)
    one, two = await _moderator(sessionmaker), await _moderator(sessionmaker)
    answers = await asyncio.gather(
        _decide(client, one, listing["id"], "approve"),
        _decide(client, two, listing["id"], "reject", {"reason_code": "weapons"}),
    )
    assert sorted(a.status_code for a in answers) == [200, 409]
    assert len(await _audit(sessionmaker, listing["id"])) == 1


async def test_remove_an_active_listing(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _listing(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    path = f"/v1/staff/listings/{listing['id']}/remove"
    refused = await client.post(path, headers=staff.headers, json={})
    assert refused.status_code == 422
    response = await client.post(path, headers=staff.headers, json={"reason_code": "counterfeit"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "removed"
    assert await _photos_deleted(sessionmaker, listing["id"])
    assert await _audit(sessionmaker, listing["id"]) == [("staff", "listing.remove", "counterfeit")]
    assert (await client.get(f"/v1/listings/{listing['id']}")).status_code == 404
