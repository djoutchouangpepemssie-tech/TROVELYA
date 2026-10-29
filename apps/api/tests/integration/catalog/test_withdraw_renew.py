"""`POST /v1/listings/{id}/withdraw` and `/renew` (P2-T04c, section 9.1, plan Q15, Q24).

The seller takes an active listing out of the shop window at any time; `renew` puts it back:
an expired listing is renewed, a withdrawn one republished. Putting back online follows the
publication's rules (Q1, a ready photo, the quota of Q24) and starts 120 new days.
"""

from datetime import datetime, timedelta
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import text

from tests.integration.catalog.test_drafts import Session, create, draft, seller
from tests.integration.catalog.test_publishing import _put_online  # pyright: ignore[reportPrivateUsage]
from tests.integration.identity.test_profile import Account, make_account


async def _published(client: AsyncClient, sessionmaker: Session) -> tuple[Account, dict[str, Any]]:
    account, zone, media = await seller(sessionmaker)
    created = await create(client, account, draft(zone, [media]))
    assert created.status_code == 201, created.text
    published = await _call(client, account, created.json()["id"], "publish")
    assert published.status_code == 200, published.text
    return account, published.json()


async def _call(
    client: AsyncClient, account: Account | None, listing_id: str, action: str
) -> Response:
    return await client.post(
        f"/v1/listings/{listing_id}/{action}", headers=account.headers if account else {}
    )


async def _history(sessionmaker: Session, listing_id: str) -> list[str]:
    async with sessionmaker() as db:
        return list(
            await db.scalars(
                text("SELECT event FROM listing_status_history WHERE listing_id = :l ORDER BY id"),
                {"l": listing_id},
            )
        )


async def test_withdraw_then_republish(client: AsyncClient, sessionmaker: Session) -> None:
    account, listing = await _published(client, sessionmaker)
    withdrawn = await _call(client, account, listing["id"], "withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"
    again = await _call(client, account, listing["id"], "withdraw")
    assert (again.status_code, again.json()["code"]) == (409, "invalid_transition")
    republished = await _call(client, account, listing["id"], "renew")
    assert republished.status_code == 200, republished.text
    back = republished.json()
    assert back["status"] == "active"
    assert back["published_at"] > listing["published_at"]
    at = datetime.fromisoformat(back["published_at"])
    assert datetime.fromisoformat(back["expires_at"]) == at + timedelta(days=120)
    assert await _history(sessionmaker, listing["id"]) == ["publish", "withdraw", "republish"]


async def test_renew_expired(client: AsyncClient, sessionmaker: Session) -> None:
    account, listing = await _published(client, sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE listings SET status = 'expired' WHERE id = :l"), {"l": listing["id"]}
        )
        await db.commit()
    renewed = await _call(client, account, listing["id"], "renew")
    assert renewed.status_code == 200, renewed.text
    back = renewed.json()
    assert back["status"] == "active"
    assert back["published_at"] > listing["published_at"]
    at = datetime.fromisoformat(back["published_at"])
    assert datetime.fromisoformat(back["expires_at"]) == at + timedelta(days=120)
    assert (await _history(sessionmaker, listing["id"]))[-1] == "renew"


async def test_renew_only_withdrawn_or_expired(client: AsyncClient, sessionmaker: Session) -> None:
    account, listing = await _published(client, sessionmaker)
    for status in ("active", "draft", "sold", "removed", "pending_review", "reserved"):
        async with sessionmaker() as db:
            await db.execute(
                text("UPDATE listings SET status = CAST(:s AS listing_status) WHERE id = :l"),
                {"s": status, "l": listing["id"]},
            )
            await db.commit()
        renewed = await _call(client, account, listing["id"], "renew")
        assert (renewed.status_code, renewed.json()["code"]) == (409, "invalid_transition"), status
        if status not in ("active", "pending_review"):  # Q29: awaiting moderation, it may
            withdrawn = await _call(client, account, listing["id"], "withdraw")
            assert withdrawn.status_code == 409, status


async def test_putting_back_online_follows_the_publication_rules(
    client: AsyncClient, sessionmaker: Session
) -> None:
    """Q24: a republication counts against the quota; Q1: an erasure in progress forbids it."""
    account, listing = await _published(client, sessionmaker)
    assert (await _call(client, account, listing["id"], "withdraw")).status_code == 200
    await _put_online(sessionmaker, account.id, ago=timedelta(hours=1), n=49)  # + the publish
    refused = await _call(client, account, listing["id"], "renew")
    assert (refused.status_code, refused.json()["code"]) == (429, "publication_limit")
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE listing_status_history SET created_at = created_at - interval '1 day'"
                " WHERE actor_id = :u"
            ),
            {"u": account.id},
        )
        await db.execute(
            text("UPDATE users SET erasure_requested_at = now() WHERE id = :u"), {"u": account.id}
        )
        await db.commit()
    forbidden = await _call(client, account, listing["id"], "renew")
    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "publish_forbidden")


async def test_withdraw_always_possible(client: AsyncClient, sessionmaker: Session) -> None:
    """Taking one's listing down is never refused for the account's state: during an erasure,
    the seller can still withdraw it."""
    account, listing = await _published(client, sessionmaker)
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE users SET erasure_requested_at = now() WHERE id = :u"), {"u": account.id}
        )
        await db.commit()
    assert (await _call(client, account, listing["id"], "withdraw")).status_code == 200


async def test_other_members_listing_404(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _published(client, sessionmaker)
    intruder = await make_account(sessionmaker, completed=True)
    for action in ("withdraw", "renew"):
        assert (await _call(client, intruder, listing["id"], action)).status_code == 404
        assert (await _call(client, None, listing["id"], action)).status_code == 401
