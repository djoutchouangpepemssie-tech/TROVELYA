"""What other modules use of anti-circumvention (section 8.16, plan Q12).

`screen` runs on a member's text before it is shown: the passages found are masked (or only
queued for review below `MASK_AT`), the detection is recorded with the original sealed, and
the text to show is returned. Never commits.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.config import Settings
from trovelya.core.gdpr import register_eraser, register_exporter
from trovelya.modules.circumvention import repository
from trovelya.modules.circumvention.models import Detection
from trovelya.modules.circumvention.rules import MASK, MASK_AT, detect, mask
from trovelya.shared.crypto import derive_key, open_sealed, seal
from trovelya.shared.ids import new_id

__all__ = ["MASK", "MASK_AT", "Detection", "detect", "mask", "open_original", "screen"]

SourceType = Literal["message", "listing", "image", "live_chat", "live_audio", "profile"]
_PURPOSE = "circumvention-original"


def _key(settings: Settings) -> bytes:
    return derive_key(settings.field_encryption_key.get_secret_value(), purpose=_PURPOSE)


def _aad(detection_id: UUID) -> bytes:
    """Binds a sealed original to its row: copied onto another one, it no longer opens."""
    return f"circumvention_detections:{detection_id}".encode()


async def screen(
    db: AsyncSession,
    *,
    user_id: UUID,
    source_type: SourceType,
    source_id: UUID,
    text: str,
    settings: Settings,
    now: datetime | None = None,
) -> str:
    """`text` as it may be shown, with the detection recorded when something was found."""
    found = detect(text)
    if not found:
        return text
    detection_id = new_id()
    confidence = max(d.confidence for d in found)
    masked = confidence >= MASK_AT
    await repository.insert_detection(
        db,
        {
            "id": detection_id,
            "user_id": user_id,
            "source_type": source_type,
            "source_id": source_id,
            "signals": sorted({d.signal for d in found}, key=[d.signal for d in found].index),
            "spans": [
                {"signal": d.signal, "start": d.start, "end": d.end, "confidence": d.confidence}
                for d in found
            ],
            "confidence": confidence,
            "action_taken": "masked" if masked else "queued",
            "review_status": "auto_confirmed" if masked else "pending",
            "original_sealed": seal(text.encode(), key=_key(settings), aad=_aad(detection_id)),
            "created_at": now or datetime.now(UTC),
        },
    )
    return mask(text, found)


def open_original(row: Mapping[str, Any], *, settings: Settings) -> str:
    """The member's original text of a detection, for the review (staff only, audited)."""
    sealed = bytes(row["original_sealed"])
    return open_sealed(sealed, key=_key(settings), aad=_aad(row["id"])).decode()


async def _export(db: AsyncSession, user_id: UUID) -> dict[str, Any]:
    return {"circumvention_detections": await repository.export_detections(db, user_id)}


register_exporter("circumvention", _export)
register_eraser("circumvention", repository.erase_detections)
