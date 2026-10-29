"""The staff's decisions, continued (P2-T05c1, review of #114): who may decide, what is checked
again at the approval, what the audit keeps."""

from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_drafts import Session
from tests.integration.catalog.test_review_queue import (
    QUEUE,
    _decide,  # pyright: ignore[reportPrivateUsage]
    _in_review,  # pyright: ignore[reportPrivateUsage]
    _listing,  # pyright: ignore[reportPrivateUsage]
    _moderator,  # pyright: ignore[reportPrivateUsage]
)
from trovelya.shared.ids import new_id


async def _execute(sessionmaker: Session, sql: str, **params: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def _row(sessionmaker: Session, sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return (await db.execute(text(sql), params)).one()


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_decisions_need_the_permission(
    client: AsyncClient, sessionmaker: Session, action: str
) -> None:
    _, listing = await _in_review(client, sessionmaker)
    support = await _moderator(sessionmaker, "staff_support")
    response = await _decide(client, support, listing["id"], action, {"reason_code": "weapons"})
    assert response.status_code == 403


async def test_remove_needs_the_permission(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _listing(client, sessionmaker)
    support = await _moderator(sessionmaker, "staff_support")
    path = f"/v1/staff/listings/{listing['id']}/remove"
    response = await client.post(path, headers=support.headers, json={"reason_code": "spam"})
    assert response.status_code == 403


async def test_role_needing_dual_approval_refused(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """No dual approval for the moderation yet: such a role may not decide alone."""
    role = f"test_dual_{new_id().hex}"
    await _execute(sessionmaker, "INSERT INTO roles VALUES (:r, 'Test')", r=role)
    await _execute(
        sessionmaker,
        "INSERT INTO role_permissions (role_key, permission_key, requires_approval)"
        " VALUES (:r, 'moderation.review', true)",
        r=role,
    )
    try:
        _, listing = await _in_review(client, sessionmaker)
        staff = await _moderator(sessionmaker, role)
        assert (await _decide(client, staff, listing["id"], "approve")).status_code == 403
    finally:  # the seed's tests read every role
        await _execute(sessionmaker, "DELETE FROM user_roles WHERE role_key = :r", r=role)
        await _execute(sessionmaker, "DELETE FROM role_permissions WHERE role_key = :r", r=role)
        await _execute(sessionmaker, "DELETE FROM roles WHERE key = :r", r=role)


@pytest.mark.parametrize("action", ["reject", "remove"])
async def test_own_listing_refused(client: AsyncClient, sessionmaker: Session, action: str) -> None:
    _, listing = await (_in_review if action == "reject" else _listing)(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    await _execute(
        sessionmaker,
        "UPDATE listings SET seller_id = :s WHERE id = :l",
        s=staff.id,
        l=listing["id"],
    )
    body = {"reason_code": "spam"}
    if action == "reject":
        response = await _decide(client, staff, listing["id"], "reject", body)
    else:
        path = f"/v1/staff/listings/{listing['id']}/remove"
        response = await client.post(path, headers=staff.headers, json=body)
    assert response.status_code == 403


async def test_approval_online_for_the_expiry_days(
    client: AsyncClient, sessionmaker: Session
) -> None:
    _, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    assert (await _decide(client, staff, listing["id"], "approve")).status_code == 200
    published, expires = await _row(
        sessionmaker, "SELECT published_at, expires_at FROM listings WHERE id = :l", l=listing["id"]
    )
    days = await _row(
        sessionmaker, "SELECT value FROM platform_settings WHERE key = 'listings.expiry_days'"
    )
    assert expires - published == timedelta(days=int(days[0]))


async def test_approval_refused_when_seller_may_no_longer_publish(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, listing = await _in_review(client, sessionmaker)
    await _execute(
        sessionmaker, "UPDATE users SET erasure_requested_at = now() WHERE id = :u", u=account.id
    )
    staff = await _moderator(sessionmaker)
    response = await _decide(client, staff, listing["id"], "approve")
    assert (response.status_code, response.json()["code"]) == (409, "publish_forbidden")
    rejected = await _decide(client, staff, listing["id"], "reject", {"reason_code": "spam"})
    assert rejected.status_code == 200  # the reviewer can still take it down


async def test_approval_refused_without_a_photo(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _in_review(client, sessionmaker)
    await _execute(
        sessionmaker,
        "UPDATE media SET deleted_at = now()"
        " WHERE id IN (SELECT media_id FROM listing_media WHERE listing_id = :l)",
        l=listing["id"],
    )
    staff = await _moderator(sessionmaker)
    response = await _decide(client, staff, listing["id"], "approve")
    assert (response.status_code, response.json()["code"]) == (409, "photo_required")


@pytest.mark.parametrize(
    ("body", "explanation"),
    [
        ({"reason_code": "misleading"}, None),
        ({"reason_code": "spam"}, None),
        (
            {"reason_code": "other", "reason_text": "  Photo d'un autre objet "},
            "Photo d'un autre objet",
        ),
    ],
)
async def test_reject_audited_before_after(
    client: AsyncClient, sessionmaker: Session, body: dict[str, str], explanation: str | None
) -> None:
    account, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    assert (await _decide(client, staff, listing["id"], "reject", body)).status_code == 200
    reason, before, after = await _row(
        sessionmaker,
        "SELECT reason, before, after FROM audit_log WHERE target_id = :l",
        l=listing["id"],
    )
    assert reason == body["reason_code"]
    assert before == {"status": "pending_review"}
    assert after == {"status": "removed", "seller_id": str(account.id), "reason_text": explanation}


async def test_remove_only_an_active_listing(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    path = f"/v1/staff/listings/{listing['id']}/remove"
    response = await client.post(path, headers=staff.headers, json={"reason_code": "spam"})
    assert (response.status_code, response.json()["code"]) == (409, "invalid_transition")


async def test_queue_shows_detections_without_the_text(
    client: AsyncClient, sessionmaker: Session
) -> None:
    _, listing = await _listing(
        client,
        sessionmaker,
        description="Pistolet ancien de collection, appelez-moi au 06 12 34 56 78.",
    )
    assert listing["status"] == "pending_review"
    staff = await _moderator(sessionmaker)
    items = (await client.get(QUEUE, headers=staff.headers, params={"limit": 100})).json()["items"]
    [item] = [item for item in items if item["id"] == listing["id"]]
    [detection] = item["detections"]
    assert set(detection) == {"part", "signals", "action_taken", "review_status"}
    assert detection["part"] == "description"
    assert "06 12 34 56 78" not in str(detection)
