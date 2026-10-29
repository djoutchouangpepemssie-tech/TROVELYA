"""The staff's decisions, continued (P2-T05c1, review of #114): who may decide, what is checked
again at the approval, what the audit keeps."""

from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text

from tests.integration.catalog.test_drafts import Session
from tests.integration.catalog.test_review_queue import (
    QUEUE,
    _decide,  # pyright: ignore[reportPrivateUsage]
    _in_review,  # pyright: ignore[reportPrivateUsage]
    _listing,  # pyright: ignore[reportPrivateUsage]
    _moderator,  # pyright: ignore[reportPrivateUsage]
)
from tests.integration.identity.test_staff_access import Staff
from trovelya.shared.ids import new_id

ACTIONS = ["approve", "reject", "remove"]
SPAM = {"reason_code": "spam"}


async def _execute(sessionmaker: Session, sql: str, **params: Any) -> None:
    async with sessionmaker() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def _row(sessionmaker: Session, sql: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        return (await db.execute(text(sql), params)).one()


async def _target(client: AsyncClient, sessionmaker: Session, action: str) -> Any:
    """A listing the action applies to: active for `remove`, awaiting review otherwise."""
    return (await (_listing if action == "remove" else _in_review)(client, sessionmaker))[1]


async def _act(client: AsyncClient, staff: Staff, listing: Any, action: str) -> Response:
    if action == "remove":
        path = f"/v1/staff/listings/{listing['id']}/remove"
        return await client.post(path, headers=staff.headers, json=SPAM)
    return await _decide(client, staff, listing["id"], action, SPAM)


@pytest.mark.parametrize("action", ACTIONS)
async def test_decisions_need_the_permission(
    client: AsyncClient, sessionmaker: Session, action: str
) -> None:
    listing = await _target(client, sessionmaker, action)
    support = await _moderator(sessionmaker, "staff_support")
    assert (await _act(client, support, listing, action)).status_code == 403


@pytest.mark.parametrize("action", ACTIONS)
async def test_own_listing_refused(client: AsyncClient, sessionmaker: Session, action: str) -> None:
    listing = await _target(client, sessionmaker, action)
    staff = await _moderator(sessionmaker)
    sql = "UPDATE listings SET seller_id = :s WHERE id = :l"
    await _execute(sessionmaker, sql, s=staff.id, l=listing["id"])
    assert (await _act(client, staff, listing, action)).status_code == 403


@pytest.mark.parametrize("action", ACTIONS)
async def test_role_needing_dual_approval_refused(
    client: AsyncClient, sessionmaker: Session, action: str
) -> None:
    """No dual approval for the moderation yet: such a role may not decide alone."""
    role = f"test_dual_{new_id().hex}"
    await _execute(sessionmaker, "INSERT INTO roles VALUES (:r, 'Test')", r=role)
    await _execute(
        sessionmaker,
        "INSERT INTO role_permissions (role_key, permission_key, requires_approval)"
        " VALUES (:r, 'moderation.review', true), (:r, 'listing.remove_any', true)",
        r=role,
    )
    try:
        listing = await _target(client, sessionmaker, action)
        staff = await _moderator(sessionmaker, role)
        assert (await _act(client, staff, listing, action)).status_code == 403
    finally:  # the seed's tests read every role
        await _execute(sessionmaker, "DELETE FROM user_roles WHERE role_key = :r", r=role)
        await _execute(sessionmaker, "DELETE FROM role_permissions WHERE role_key = :r", r=role)
        await _execute(sessionmaker, "DELETE FROM roles WHERE key = :r", r=role)


async def test_approval_online_for_the_expiry_days(
    client: AsyncClient, sessionmaker: Session
) -> None:
    _, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    assert (await _decide(client, staff, listing["id"], "approve")).status_code == 200
    sql = "SELECT published_at, expires_at FROM listings WHERE id = :l"
    published, expires = await _row(sessionmaker, sql, l=listing["id"])
    sql = "SELECT value FROM platform_settings WHERE key = 'listings.expiry_days'"
    assert expires - published == timedelta(days=int((await _row(sessionmaker, sql))[0]))


ERASING = "UPDATE users SET erasure_requested_at = now() WHERE id = :u"
NO_PHOTO = "UPDATE media SET deleted_at = now() WHERE id IN (SELECT media_id FROM listing_media"


@pytest.mark.parametrize(
    ("change", "code"), [(ERASING, "publish_forbidden"), (NO_PHOTO, "photo_required")]
)
async def test_approval_checks_the_listing_again(
    client: AsyncClient, sessionmaker: Session, change: str, code: str
) -> None:
    """The seller may no longer publish, or the photo is gone: the reviewer rejects it instead."""
    account, listing = await _in_review(client, sessionmaker)
    if change == ERASING:
        await _execute(sessionmaker, change, u=account.id)
    else:
        await _execute(sessionmaker, change + " WHERE listing_id = :l)", l=listing["id"])
    staff = await _moderator(sessionmaker)
    response = await _decide(client, staff, listing["id"], "approve")
    assert (response.status_code, response.json()["code"]) == (409, code)
    assert (await _decide(client, staff, listing["id"], "reject", SPAM)).status_code == 200


@pytest.mark.parametrize(
    ("body", "explanation"),
    [
        ({"reason_code": "misleading"}, None),
        (SPAM, None),
        ({"reason_code": "other", "reason_text": " Autre objet "}, "Autre objet"),
    ],
)
async def test_reject_audited_before_after(
    client: AsyncClient, sessionmaker: Session, body: dict[str, str], explanation: str | None
) -> None:
    account, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    assert (await _decide(client, staff, listing["id"], "reject", body)).status_code == 200
    sql = "SELECT reason, before, after FROM audit_log WHERE target_id = :l"
    reason, before, after = await _row(sessionmaker, sql, l=listing["id"])
    assert (reason, before) == (body["reason_code"], {"status": "pending_review"})
    # No free text kept 10 years: the explanation stays in the listing's history.
    assert after == {"status": "removed", "seller_id": str(account.id)}
    sql = (
        "SELECT reason_text FROM listing_status_history WHERE listing_id = :l AND event = 'reject'"
    )
    assert (await _row(sessionmaker, sql, l=listing["id"]))[0] == explanation


async def test_remove_only_an_active_listing(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _in_review(client, sessionmaker)
    response = await _act(client, await _moderator(sessionmaker), listing, "remove")
    assert (response.status_code, response.json()["code"]) == (409, "invalid_transition")


async def test_queue_shows_detections_without_the_text(
    client: AsyncClient, sessionmaker: Session
) -> None:
    description = "Pistolet ancien de collection, appelez-moi au 06 12 34 56 78."
    _, listing = await _listing(client, sessionmaker, description=description)
    assert listing["status"] == "pending_review"
    staff = await _moderator(sessionmaker)
    items = (await client.get(QUEUE, headers=staff.headers, params={"limit": 100})).json()["items"]
    [detection] = next(item for item in items if item["id"] == listing["id"])["detections"]
    assert set(detection) == {"part", "signals", "action_taken", "review_status"}
    assert detection["part"] == "description"
    assert "06 12 34 56 78" not in str(detection)


async def test_owner_no_longer_gets_a_removed_photo(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """Q40: once removed by the moderation, the photo is served to nobody, its owner included."""
    account, listing = await _in_review(client, sessionmaker)
    staff = await _moderator(sessionmaker)
    assert (await _decide(client, staff, listing["id"], "reject", SPAM)).status_code == 200
    sql = "SELECT media_id FROM listing_media WHERE listing_id = :l"
    [media_id] = await _row(sessionmaker, sql, l=listing["id"])
    media = await client.get(f"/v1/media/{media_id}", headers=account.headers)
    assert (media.status_code, media.json()["variants"]) == (200, [])
