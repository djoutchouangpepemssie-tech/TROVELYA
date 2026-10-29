"""What other modules use of anti-circumvention (section 8.16, plan Q12, Q35).

`screen` runs on a member's text before it is shown: the passages found are masked (or only
queued for review below `MASK_AT`), the detections are recorded with the original sealed, and
the text to show is returned. One row for what was masked (confirmed automatically) and one
for what goes to review, so a doubtful passage is never confirmed with a sure one. Never
commits.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.gdpr import register_eraser, register_exporter
from trovelya.modules.circumvention import repository
from trovelya.modules.circumvention.models import Detection
from trovelya.modules.circumvention.rules import MASK, MASK_AT, detect, mask
from trovelya.shared.audit import record_audit
from trovelya.shared.clock import Clock
from trovelya.shared.crypto import SealError, derive_key, open_sealed, seal
from trovelya.shared.ids import new_id

__all__ = [
    "MASK",
    "MASK_AT",
    "Detection",
    "detect",
    "mask",
    "open_original",
    "screen",
]

logger = structlog.get_logger(__name__)

SourceType = Literal["message", "listing", "image", "live_chat", "live_audio", "profile"]
_PURPOSE = "circumvention-original"


def _key(settings: Settings) -> bytes:
    return derive_key(settings.field_encryption_key.get_secret_value(), purpose=_PURPOSE)


def _aad(row: Mapping[str, Any]) -> bytes:
    """Binds a sealed original to its row, its member and its source: copied onto another
    row, or the row moved to another member or source, it no longer opens."""
    return (
        f"circumvention_detections:{row['id']}:{row['user_id']}"
        f":{row['source_type']}:{row['source_id']}"
    ).encode()


async def _record(
    db: AsyncSession,
    found: Sequence[Detection],
    *,
    masked: bool,
    base: Mapping[str, Any],
    text: str,
    settings: Settings,
) -> None:
    row = {**base, "id": new_id()}
    await repository.insert_detection(
        db,
        {
            **row,
            "signals": list(dict.fromkeys(d.signal for d in found)),
            "spans": [
                {"signal": d.signal, "start": d.start, "end": d.end, "confidence": d.confidence}
                for d in found
            ],
            "confidence": max(d.confidence for d in found),
            "action_taken": "masked" if masked else "queued",
            "review_status": "auto_confirmed" if masked else "pending",
            "original_sealed": seal(text.encode(), key=_key(settings), aad=_aad(row)),
        },
    )


async def screen(
    db: AsyncSession,
    *,
    user_id: UUID,
    source_type: SourceType,
    source_id: UUID,
    text: str,
    settings: Settings,
    clock: Clock,
) -> str:
    """`text` as it may be shown, with the detections recorded when something was found."""
    found = detect(text)
    base = {
        "user_id": user_id,
        "source_type": source_type,
        "source_id": source_id,
        "created_at": clock.now(),
    }
    for masked in (True, False):
        part = [d for d in found if (d.confidence >= MASK_AT) is masked]
        if part:
            await _record(db, part, masked=masked, base=base, text=text, settings=settings)
    return mask(text, found)


async def open_original(
    db: AsyncSession, row: Mapping[str, Any], *, staff_id: UUID, settings: Settings
) -> str:
    """The member's original text of a detection, for the review: the reading is written in
    the audit log in the caller's transaction (who read which detection)."""
    original = open_sealed(
        bytes(row["original_sealed"]), key=_key(settings), aad=_aad(row)
    ).decode()
    await record_audit(
        db,
        actor_type="staff",
        actor_id=staff_id,
        action="circumvention.original_read",
        target_type="circumvention_detection",
        target_id=str(row["id"]),
    )
    return original


async def _export(db: AsyncSession, user_id: UUID, settings: Settings) -> dict[str, Any]:
    """Q35: the member's detections with the original text they wrote (right of access). A
    text that no longer opens (a damaged row, a lost key) is said unavailable: it never
    stops the rest of the export."""
    rows = await repository.export_detections(db, user_id)
    for row in rows:
        sealed = row.pop("original_sealed")
        try:
            row["original_text"] = open_sealed(
                bytes(sealed), key=_key(settings), aad=_aad({**row, "user_id": user_id})
            ).decode()
        except SealError:
            logger.warning("circumvention.original_unavailable", detection_id=str(row["id"]))
            row["original_text"] = None
        row["original_unavailable"] = row["original_text"] is None
    return {"circumvention_detections": rows}


register_exporter("circumvention", _export)
register_eraser("circumvention", repository.erase_detections)
