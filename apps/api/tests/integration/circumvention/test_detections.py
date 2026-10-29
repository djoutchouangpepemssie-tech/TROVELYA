"""Detections recorded (section 7.10, plan P2-T05a, Q12, Q35, Q36): what was found, where, how
sure, and the member's original text sealed (AES-256-GCM) for the review; never a contact
detail in clear in the table. What was masked and what goes to review are two rows. Exported
with the original text, erased with the account, purged 180 days after once reviewed."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers, registered_exporters
from trovelya.modules.circumvention.service import MASK, open_original, screen
from trovelya.modules.circumvention.tasks import purge_old_detections
from trovelya.shared.clock import FixedClock
from trovelya.shared.crypto import SealError
from trovelya.shared.ids import new_id

Session = async_sessionmaker[AsyncSession]
SETTINGS = make_settings()
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


async def _screen(
    sessionmaker: Session, user_id: UUID, body: str, *, now: datetime = NOW
) -> tuple[UUID, str]:
    source_id = new_id()
    async with sessionmaker() as db:
        shown = await screen(
            db,
            user_id=user_id,
            source_type="listing",
            source_id=source_id,
            text=body,
            settings=SETTINGS,
            clock=FixedClock(now),
        )
        await db.commit()
    return source_id, shown


async def _rows(sessionmaker: Session, source_id: UUID) -> list[dict[str, Any]]:
    async with sessionmaker() as db:
        result = await db.execute(
            text("SELECT * FROM circumvention_detections WHERE source_id = :s ORDER BY id"),
            {"s": source_id},
        )
        return [dict(row) for row in result.mappings()]


async def _open(sessionmaker: Session, row: dict[str, Any]) -> str:
    async with sessionmaker() as db:
        original = await open_original(db, row, staff_id=new_id(), settings=SETTINGS)
        await db.commit()
    return original


async def test_original_stored_encrypted(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    original = "Lampe opaline. Appelez le 06 12 34 56 78 ou jean@gmail.com"
    source_id, shown = await _screen(sessionmaker, member.id, original)
    assert shown == f"Lampe opaline. Appelez le {MASK} ou {MASK}"
    [row] = await _rows(sessionmaker, source_id)
    assert row["signals"] == ["phone", "email"]
    assert (row["action_taken"], row["review_status"]) == ("masked", "auto_confirmed")
    assert float(row["confidence"]) == 0.95
    assert row["created_at"] == NOW
    # No contact detail in clear anywhere in the row: only positions, signals, the sealed text.
    in_clear = repr({k: v for k, v in row.items() if k != "original_sealed"})
    for leak in ("06 12", "0612", "jean", "gmail"):
        assert leak not in in_clear, leak
    assert b"0612" not in bytes(row["original_sealed"])
    assert row["matched_spans"] == [
        {"signal": "phone", "start": 26, "end": 40, "confidence": 0.95},
        {"signal": "email", "start": 44, "end": 58, "confidence": 0.95},
    ]
    assert await _open(sessionmaker, row) == original


async def test_mixed_confidence_two_rows(sessionmaker: Session) -> None:
    """A doubtful passage is never confirmed with a sure one: it goes to review on its own."""
    member = await make_account(sessionmaker, completed=True)
    body = "Tailles 36 38 40 42 sinon jean@gmail.com"
    source_id, shown = await _screen(sessionmaker, member.id, body)
    assert shown == f"Tailles 36 38 40 42 sinon {MASK}"
    rows = await _rows(sessionmaker, source_id)
    assert sorted((r["signals"][0], r["action_taken"], r["review_status"]) for r in rows) == [
        ("email", "masked", "auto_confirmed"),
        ("obfuscated_number", "queued", "pending"),
    ]
    for row in rows:
        assert await _open(sessionmaker, row) == body


async def test_low_confidence_queued_not_masked(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    source_id, shown = await _screen(sessionmaker, member.id, "Tailles disponibles 36 38 40 42")
    assert shown == "Tailles disponibles 36 38 40 42"
    [row] = await _rows(sessionmaker, source_id)
    assert (row["action_taken"], row["review_status"]) == ("queued", "pending")
    assert float(row["confidence"]) == 0.5


async def test_nothing_found_nothing_recorded(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    source_id, shown = await _screen(sessionmaker, member.id, "Lot de 12 livres, très bon état")
    assert shown == "Lot de 12 livres, très bon état"
    assert await _rows(sessionmaker, source_id) == []


async def test_reading_the_original_is_audited(sessionmaker: Session) -> None:
    member = await make_account(sessionmaker, completed=True)
    source_id, _ = await _screen(sessionmaker, member.id, "Écrivez sur WhatsApp")
    [row] = await _rows(sessionmaker, source_id)
    staff_id = new_id()
    async with sessionmaker() as db:
        await open_original(db, row, staff_id=staff_id, settings=SETTINGS)
        await db.commit()
        sql = "SELECT actor_type, actor_id, action FROM audit_log WHERE target_id = :t"
        audit = (await db.execute(text(sql), {"t": str(row["id"])})).one()
    assert tuple(audit) == ("staff", staff_id, "circumvention.original_read")


async def test_sealed_original_bound_to_its_row(sessionmaker: Session) -> None:
    """Copied onto another row, moved to another member, or opened with another key: refused."""
    member = await make_account(sessionmaker, completed=True)
    first, _ = await _screen(sessionmaker, member.id, "Écrivez sur WhatsApp")
    second, _ = await _screen(sessionmaker, member.id, "Paiement par Lydia possible")
    [row] = await _rows(sessionmaker, first)
    [other] = await _rows(sessionmaker, second)
    stranger = make_settings(field_encryption_key="b" * 64)
    async with sessionmaker() as db:
        for tampered, settings in (
            ({**other, "original_sealed": row["original_sealed"]}, SETTINGS),
            ({**row, "user_id": new_id()}, SETTINGS),
            (row, stranger),
        ):
            with pytest.raises(SealError):
                await open_original(db, tampered, staff_id=new_id(), settings=settings)


@pytest.mark.parametrize(
    ("column", "value"),
    [("signals", "fax"), ("confidence", "1.5"), ("review_status", "confirmed")],
)
async def test_checks_refuse_inconsistent_rows(
    sessionmaker: Session, column: str, value: str
) -> None:
    """An unknown signal, a confidence above 1, a confirmation without a reviewer."""
    member = await make_account(sessionmaker, completed=True)
    source_id, _ = await _screen(sessionmaker, member.id, "Écrivez sur WhatsApp")
    sql = {
        "signals": "UPDATE circumvention_detections SET signals = ARRAY[CAST(:v AS text)]",
        "confidence": "UPDATE circumvention_detections SET confidence = CAST(:v AS numeric)",
        "review_status": "UPDATE circumvention_detections SET review_status = :v",
    }[column]
    async with sessionmaker() as db:
        with pytest.raises(IntegrityError):
            await db.execute(text(sql + " WHERE source_id = :s"), {"v": value, "s": source_id})


async def test_exported_with_the_original_and_erased(sessionmaker: Session) -> None:
    """Q35: the export carries the original text the member wrote, never the sealed blob;
    the erasure takes the member's detections and no one else's."""
    member = await make_account(sessionmaker, completed=True)
    other = await make_account(sessionmaker, completed=True)
    source_id, _ = await _screen(sessionmaker, member.id, "Écrivez sur WhatsApp")
    kept, _ = await _screen(sessionmaker, other.id, "Écrivez sur WhatsApp")
    async with sessionmaker() as db:
        exported = await registered_exporters()["circumvention"](db, member.id, SETTINGS)
    [detection] = exported["circumvention_detections"]
    assert detection["signals"] == ["payment_app"]
    assert detection["original_text"] == "Écrivez sur WhatsApp"
    assert detection["original_unavailable"] is False
    assert "original_sealed" not in detection
    assert detection["matched_spans"] == [
        {"signal": "payment_app", "start": 12, "end": 20, "confidence": 0.9}
    ]
    async with sessionmaker() as db:
        await registered_erasers()["circumvention"](db, member.id)
        await db.commit()
    assert await _rows(sessionmaker, source_id) == []
    assert len(await _rows(sessionmaker, kept)) == 1


async def test_reviewed_detections_purged_after_180_days(sessionmaker: Session) -> None:
    """Q36: past `retention.circumvention_detection_days`, what was confirmed goes; what
    still awaits its review stays; a younger detection stays."""
    member = await make_account(sessionmaker, completed=True)
    old = NOW - timedelta(days=181)
    confirmed, _ = await _screen(sessionmaker, member.id, "Écrivez sur WhatsApp", now=old)
    pending, _ = await _screen(sessionmaker, member.id, "Tailles 36 38 40 42", now=old)
    young, _ = await _screen(
        sessionmaker, member.id, "Écrivez sur WhatsApp", now=NOW - timedelta(days=179)
    )
    await purge_old_detections(sessionmaker, clock=FixedClock(NOW))
    assert await _rows(sessionmaker, confirmed) == []
    assert len(await _rows(sessionmaker, pending)) == 1
    assert len(await _rows(sessionmaker, young)) == 1


async def test_late_review_kept_180_days_after_it(sessionmaker: Session) -> None:
    """A detection reviewed long after it was found keeps its evidence 180 days from the
    review (the window of the sanctions, the time to contest)."""
    member = await make_account(sessionmaker, completed=True)
    source_id, _ = await _screen(
        sessionmaker, member.id, "Tailles 36 38 40 42", now=NOW - timedelta(days=250)
    )
    async with sessionmaker() as db:
        await db.execute(
            text(
                "UPDATE circumvention_detections SET review_status = 'confirmed',"
                " reviewed_by = :staff, reviewed_at = :at WHERE source_id = :s"
            ),
            {"staff": new_id(), "at": NOW - timedelta(days=10), "s": source_id},
        )
        await db.commit()
    await purge_old_detections(sessionmaker, clock=FixedClock(NOW))
    assert len(await _rows(sessionmaker, source_id)) == 1


async def test_unreadable_original_never_stops_the_export(sessionmaker: Session) -> None:
    """A damaged sealed text is said unavailable; the rest of the export is built."""
    member = await make_account(sessionmaker, completed=True)
    source_id, _ = await _screen(sessionmaker, member.id, "Écrivez sur WhatsApp")
    async with sessionmaker() as db:
        await db.execute(
            text("UPDATE circumvention_detections SET original_sealed = :b WHERE source_id = :s"),
            {"b": b"\x00" * 40, "s": source_id},
        )
        await db.commit()
        exported = await registered_exporters()["circumvention"](db, member.id, SETTINGS)
    [detection] = exported["circumvention_detections"]
    assert (detection["original_text"], detection["original_unavailable"]) == (None, True)
    assert detection["signals"] == ["payment_app"]


async def test_same_passages_found_again_recorded_once(sessionmaker: Session) -> None:
    """A listing put back online is screened again: the same passages are not a new case."""
    member = await make_account(sessionmaker, completed=True)
    source_id = new_id()
    for _ in range(3):
        async with sessionmaker() as db:
            await screen(
                db,
                user_id=member.id,
                source_type="listing",
                source_id=source_id,
                text="Paiement par virement uniquement.",
                settings=SETTINGS,
                clock=FixedClock(NOW),
            )
            await db.commit()
    assert len(await _rows(sessionmaker, source_id)) == 1
