"""Moderation of a listing put online (P2-T05b1, 8.16, 8.17, plan Q12, Q29, Q32 to Q34):
prohibited item refused with its reason, ambiguous term or restricted category to review,
contact details masked with a reminder; renewing is moderated; a listing in review withdrawn."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.catalog.test_drafts import Session, create, draft, seller
from tests.integration.catalog.test_withdraw_renew import _call  # pyright: ignore[reportPrivateUsage]
from trovelya.modules.circumvention.service import MASK


async def _put_online(
    client: AsyncClient, sessionmaker: Session, **changes: Any
) -> tuple[Any, dict[str, Any]]:
    account, zone, media = await seller(sessionmaker)
    created = await create(client, account, draft(zone, [media], **changes))
    assert created.status_code == 201, created.text
    published = await _call(client, account, created.json()["id"], "publish")
    assert published.status_code == 200, published.text
    return account, published.json()


async def _history(sessionmaker: Session, listing_id: str) -> list[tuple[Any, ...]]:
    async with sessionmaker() as db:
        rows = await db.execute(
            text(
                "SELECT event, to_status, actor_kind, reason_code FROM listing_status_history"
                " WHERE listing_id = :l ORDER BY id"
            ),
            {"l": listing_id},
        )
        return [tuple(row) for row in rows]


async def _set(sessionmaker: Session, listing_id: str, sql: str) -> None:
    statements = {
        "whisky": "UPDATE listings SET description = 'Bouteille de whisky 12 ans d''âge'",
        "pistolet": "UPDATE listings SET description = 'Pistolet ancien, belle patine, rare.'",
        "expired": "UPDATE listings SET status = 'expired'",
    }
    async with sessionmaker() as db:
        await db.execute(text(statements[sql] + " WHERE id = :l"), {"l": listing_id})
        await db.commit()


async def test_clean_listing_online_without_notice(
    client: AsyncClient, sessionmaker: Session
) -> None:
    _, listing = await _put_online(client, sessionmaker)
    assert listing["status"] == "active"
    assert listing["moderation"] == {"outcome": "online", "reasons": [], "notice": None}


async def test_prohibited_refused_with_reason(client: AsyncClient, sessionmaker: Session) -> None:
    """Q33, Q34: refused through review and rejection by the platform, with the reason."""
    _, listing = await _put_online(
        client,
        sessionmaker,
        title="Bouteille de whisky",
        description="Whisky écossais 12 ans d'âge.",
    )
    assert listing["status"] == "removed"
    assert listing["published_at"] is None
    assert listing["moderation"] == {
        "outcome": "refused",
        "reasons": [{"code": "alcohol", "label": "Alcool"}],
        "notice": None,
    }
    assert await _history(sessionmaker, listing["id"]) == [
        ("submit_for_review", "pending_review", "user", "alcohol"),
        ("reject", "removed", "system", "alcohol"),
    ]


async def test_ambiguous_term_goes_to_review(client: AsyncClient, sessionmaker: Session) -> None:
    _, listing = await _put_online(
        client, sessionmaker, description="Pistolet ancien de collection, belle patine."
    )
    assert listing["status"] == "pending_review"
    assert listing["moderation"]["outcome"] == "review"
    assert listing["moderation"]["reasons"] == [{"code": "weapons", "label": "Armes et munitions"}]
    assert await _history(sessionmaker, listing["id"]) == [
        ("submit_for_review", "pending_review", "user", "weapons"),
    ]


async def test_restricted_category_goes_to_review(
    client: AsyncClient, sessionmaker: Session
) -> None:
    _, listing = await _put_online(
        client,
        sessionmaker,
        title="Entrée stade, tribune nord",
        description="Match de samedi, tribune nord, rang 12, très bonne vue.",
        category="autres.billetterie.sport",
        attributes={},
    )
    assert listing["status"] == "pending_review"
    assert listing["moderation"]["reasons"] == [
        {"code": "restricted_category", "label": "Catégorie vérifiée par un humain"}
    ]


async def test_contacts_masked_and_published(client: AsyncClient, sessionmaker: Session) -> None:
    """Q12: the passage masked in the listing itself, the listing published, a reminder in the
    answer, the detection recorded for the review."""
    _, listing = await _put_online(
        client, sessionmaker, description="Robe portée deux fois, appelez le 06 12 34 56 78."
    )
    assert listing["status"] == "active"
    assert listing["description"] == f"Robe portée deux fois, appelez le {MASK}."
    assert listing["moderation"]["outcome"] == "online"
    assert "messagerie" in listing["moderation"]["notice"]
    async with sessionmaker() as db:
        stored = await db.scalar(
            text("SELECT description FROM listings WHERE id = :l"), {"l": listing["id"]}
        )
        detections = await db.scalar(
            text(
                "SELECT count(*) FROM circumvention_detections"
                " WHERE source_type = 'listing' AND source_id = :l"
            ),
            {"l": listing["id"]},
        )
    assert "06 12" not in stored
    assert detections == 1


async def test_renew_is_moderated(client: AsyncClient, sessionmaker: Session) -> None:
    """Q32: the list may have changed, or the listing: putting it back online is moderated."""
    account, listing = await _put_online(client, sessionmaker)
    assert (await _call(client, account, listing["id"], "withdraw")).status_code == 200
    await _set(sessionmaker, listing["id"], "whisky")
    republished = await _call(client, account, listing["id"], "renew")
    assert republished.status_code == 200, republished.text
    assert republished.json()["status"] == "removed"
    assert (await _history(sessionmaker, listing["id"]))[-2:] == [
        ("submit_for_review", "pending_review", "user", "alcohol"),
        ("reject", "removed", "system", "alcohol"),
    ]


async def test_expired_listing_renewed_to_review(
    client: AsyncClient, sessionmaker: Session
) -> None:
    account, listing = await _put_online(client, sessionmaker)
    await _set(sessionmaker, listing["id"], "expired")
    await _set(sessionmaker, listing["id"], "pistolet")
    renewed = await _call(client, account, listing["id"], "renew")
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["status"] == "pending_review"


async def test_withdraw_pending_review(client: AsyncClient, sessionmaker: Session) -> None:
    """Q29: the seller takes back a listing awaiting the moderation's decision."""
    account, listing = await _put_online(
        client, sessionmaker, description="Pistolet ancien de collection, belle patine."
    )
    withdrawn = await _call(client, account, listing["id"], "withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"
    assert (await _history(sessionmaker, listing["id"]))[-1][:2] == ("withdraw", "withdrawn")
