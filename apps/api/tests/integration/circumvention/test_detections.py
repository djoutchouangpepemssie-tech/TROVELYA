"""Detections recorded (section 7.10, plan P2-T05a, Q12): what was found, where, how sure,
and the member's original text sealed (AES-256-GCM) for the review; never a contact detail in
clear in the table. Exported and erased with the account (GDPR)."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers, registered_exporters
from trovelya.modules.circumvention.service import MASK, open_original, screen
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]
SETTINGS = make_settings()


async def _rows(sessionmaker: Session, source_id: UUID) -> list[dict[str, object]]:
    async with sessionmaker() as db:
        result = await db.execute(
            text("SELECT * FROM circumvention_detections WHERE source_id = :s"), {"s": source_id}
        )
        return [dict(row) for row in result.mappings()]


async def test_original_stored_encrypted(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    source_id = new_id()
    original = "Lampe opaline. Appelez le 06 12 34 56 78 ou jean@gmail.com"
    async with sessionmaker() as db:
        shown = await screen(
            db,
            user_id=member.id,
            source_type="listing",
            source_id=source_id,
            text=original,
            settings=SETTINGS,
        )
        await db.commit()
    assert shown == f"Lampe opaline. Appelez le {MASK} ou {MASK}"
    [row] = await _rows(sessionmaker, source_id)
    assert set(row["signals"]) == {"phone", "email"}  # type: ignore[arg-type]
    assert (row["action_taken"], row["review_status"]) == ("masked", "auto_confirmed")
    assert row["confidence"] is not None
    # No contact detail in clear anywhere in the row: only positions, signals, the sealed text.
    in_clear = repr({k: v for k, v in row.items() if k != "original_sealed"})
    for leak in ("06 12", "0612", "jean", "gmail"):
        assert leak not in in_clear, leak
    assert b"0612" not in bytes(row["original_sealed"])  # type: ignore[arg-type]
    assert open_original(row, settings=SETTINGS) == original
    spans = row["matched_spans"]
    assert [(s["signal"], s["start"], s["end"]) for s in spans] == [  # type: ignore[union-attr]
        ("phone", 26, 40),
        ("email", 44, 58),
    ]


async def test_low_confidence_queued_not_masked(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    source_id = new_id()
    async with sessionmaker() as db:
        shown = await screen(
            db,
            user_id=member.id,
            source_type="listing",
            source_id=source_id,
            text="Tailles disponibles 36 38 40 42",
            settings=SETTINGS,
        )
        await db.commit()
    assert shown == "Tailles disponibles 36 38 40 42"
    [row] = await _rows(sessionmaker, source_id)
    assert (row["action_taken"], row["review_status"]) == ("queued", "pending")


async def test_nothing_found_nothing_recorded(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    source_id = new_id()
    async with sessionmaker() as db:
        shown = await screen(
            db,
            user_id=member.id,
            source_type="listing",
            source_id=source_id,
            text="Lot de 12 livres, très bon état",
            settings=SETTINGS,
        )
        await db.commit()
    assert shown == "Lot de 12 livres, très bon état"
    assert await _rows(sessionmaker, source_id) == []


async def test_exported_and_erased_with_the_account(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    source_id = new_id()
    async with sessionmaker() as db:
        await screen(
            db,
            user_id=member.id,
            source_type="listing",
            source_id=source_id,
            text="Écrivez sur WhatsApp",
            settings=SETTINGS,
        )
        await db.commit()
        exported = await registered_exporters()["circumvention"](db, member.id)
    [detection] = exported["circumvention_detections"]
    assert detection["signals"] == ["payment_app"]
    assert "original_sealed" not in detection
    async with sessionmaker() as db:
        await registered_erasers()["circumvention"](db, member.id)
        await db.commit()
    assert await _rows(sessionmaker, source_id) == []
