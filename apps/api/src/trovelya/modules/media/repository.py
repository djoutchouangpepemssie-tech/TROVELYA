"""SQL of the media module. Only this module's service reads or writes these tables."""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

# What a member gets in the GDPR export: every file they sent, deleted ones included, with
# what is known of it; not the storage keys (internal) nor the image hashes (fraud detection).
_EXPORT_MEDIA = text(
    "SELECT id, kind, purpose, mime_type, bytes, width, height, duration_ms, captured_at,"
    " status, rejection_reason, exif_stripped, moderation,"
    " (SELECT coalesce(jsonb_agg(jsonb_build_object('format', v->'format', 'width', v->'width',"
    " 'height', v->'height')), '[]') FROM jsonb_array_elements(variants) v) AS variants,"
    " created_at, updated_at, deleted_at"
    " FROM media WHERE owner_id = :user_id ORDER BY created_at"
)


async def export_media(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    rows = await db.execute(_EXPORT_MEDIA, {"user_id": user_id})
    return [dict(row) for row in rows.mappings()]


async def setting_int(db: AsyncSession, key: str) -> int:
    """A [PARAM] of `platform_settings`, seeded by the migrations (missing = a bug)."""
    value = await db.scalar(
        text("SELECT value FROM platform_settings WHERE key = :key"), {"key": key}
    )
    if value is None:
        raise LookupError(f"platform setting {key} is missing")
    return int(value)


async def lock_uploads_of(db: AsyncSession, owner_id: UUID) -> None:
    """Serialises one member's upload requests, so two at once cannot both pass the quota."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('media.uploads:' || :owner, 0))"),
        {"owner": str(owner_id)},
    )


async def count_uploads_since(db: AsyncSession, owner_id: UUID, since: datetime) -> int:
    count = await db.scalar(
        text("SELECT count(*) FROM media WHERE owner_id = :owner AND created_at > :since"),
        {"owner": owner_id, "since": since},
    )
    return int(count or 0)


async def insert_upload(
    db: AsyncSession,
    *,
    media_id: UUID,
    owner_id: UUID,
    purpose: str,
    storage_key: str,
    mime_type: str,
    size: int,
    now: datetime,
) -> None:
    await db.execute(
        text(
            "INSERT INTO media (id, owner_id, kind, purpose, storage_key, mime_type, bytes,"
            " status, created_at, updated_at)"
            " VALUES (:id, :owner, 'image', :purpose, :key, :mime, :size, 'uploading', :now, :now)"
        ),
        {
            "id": media_id,
            "owner": owner_id,
            "purpose": purpose,
            "key": storage_key,
            "mime": mime_type,
            "size": size,
            "now": now,
        },
    )


async def start_processing(db: AsyncSession, media_id: UUID, owner_id: UUID) -> str | None:
    """`uploading` → `processing` for the owner's media. Returns "started", or the status found
    when it was not `uploading`, or None when the media is not theirs or does not exist."""
    started = await db.scalar(
        text(
            "UPDATE media SET status = 'processing' WHERE id = :id AND owner_id = :owner"
            " AND status = 'uploading' AND deleted_at IS NULL RETURNING id"
        ),
        {"id": media_id, "owner": owner_id},
    )
    if started is not None:
        return "started"
    return await db.scalar(
        text(
            "SELECT status FROM media WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
        ),
        {"id": media_id, "owner": owner_id},
    )


_OWNED_MEDIA = text(
    "SELECT id, purpose, mime_type, status, width, height, variants, rejection_reason,"
    " quarantined_at FROM media WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
)
_OWNED_MEDIA_FOR_SHARE = text(
    "SELECT id, purpose, mime_type, status, width, height, variants, rejection_reason"
    " FROM media WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL FOR SHARE"
)


async def owned_media(
    db: AsyncSession, media_id: UUID, owner_id: UUID, *, lock: bool = False
) -> Row[Any] | None:
    """`lock`: held FOR SHARE until the transaction ends, so the purge cannot delete a photo
    being chosen as an avatar or attached to a listing (see `mark_for_purge`)."""
    query = _OWNED_MEDIA_FOR_SHARE if lock else _OWNED_MEDIA
    return (await db.execute(query, {"id": media_id, "owner": owner_id})).one_or_none()


async def media_to_process(db: AsyncSession, media_id: UUID) -> Row[Any] | None:
    """The row the worker works from; None when it does not exist or was deleted."""
    return (
        await db.execute(
            text(
                "SELECT id, owner_id, purpose, status, mime_type, storage_key FROM media"
                " WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": media_id},
        )
    ).one_or_none()


async def mark_rejected(db: AsyncSession, media_id: UUID, reason: str) -> bool:
    """`processing` → `rejected`; False when another run already decided."""
    done = await db.scalar(
        text(
            "UPDATE media SET status = 'rejected', rejection_reason = :reason"
            " WHERE id = :id AND status = 'processing' AND deleted_at IS NULL RETURNING id"
        ),
        {"id": media_id, "reason": reason},
    )
    return done is not None


async def mark_ready(
    db: AsyncSession,
    media_id: UUID,
    *,
    width: int,
    height: int,
    sha256: bytes,
    perceptual_hash: int,
    variants: list[dict[str, Any]],
    moderation: dict[str, Any],
) -> bool:
    """`processing` → `ready`; False when another run already decided."""
    done = await db.scalar(
        text(
            "UPDATE media SET status = 'ready', width = :width, height = :height,"
            " sha256 = :sha256, perceptual_hash = :hash, exif_stripped = true,"
            " variants = CAST(:variants AS jsonb), moderation = moderation || CAST(:mod AS jsonb)"
            " WHERE id = :id AND status = 'processing' AND deleted_at IS NULL RETURNING id"
        ),
        {
            "id": media_id,
            "width": width,
            "height": height,
            "sha256": sha256,
            "hash": perceptual_hash,
            "variants": json.dumps(variants),
            "mod": json.dumps(moderation),
        },
    )
    return done is not None


async def oldest_similar_media(
    db: AsyncSession, perceptual_hash: int, max_distance: int
) -> Row[Any] | None:
    """The first ready listing photo (id, owner_id) within `max_distance` bits of this dHash.

    A full scan, fine while P2 holds few photos; before launch, index bands of the hash
    (7 bands: two hashes 6 bits apart share at least one) — recorded in the P2 plan."""
    return (
        await db.execute(
            text(
                "SELECT id, owner_id FROM media WHERE status = 'ready' AND deleted_at IS NULL"
                " AND purpose = 'listing' AND perceptual_hash IS NOT NULL"
                " AND bit_count((perceptual_hash # :hash)::bit(64)) <= :distance"
                " ORDER BY created_at, id LIMIT 1"
            ),
            {"hash": perceptual_hash, "distance": max_distance},
        )
    ).first()


async def mark_attempt(db: AsyncSession, media_id: UUID) -> None:
    """An attempt starts now: `updated_at` is when the media was last worked on."""
    await db.execute(
        text("UPDATE media SET updated_at = now() WHERE id = :id AND status = 'processing'"),
        {"id": media_id},
    )


async def stuck_in_processing(db: AsyncSession, before: datetime) -> list[tuple[UUID, datetime]]:
    """Media `processing` with no attempt since `before`: (id, created_at)."""
    rows = await db.execute(
        text(
            "SELECT id, created_at FROM media WHERE status = 'processing' AND deleted_at IS NULL"
            " AND updated_at < :before ORDER BY updated_at LIMIT 100"
        ),
        {"before": before},
    )
    return [(row[0], row[1]) for row in rows]


async def mark_deleted(db: AsyncSession, media_id: UUID, now: datetime) -> None:
    """Withdrawn from view now; its files go with the purge (P2-T02c)."""
    await db.execute(
        text("UPDATE media SET deleted_at = :now WHERE id = :id AND deleted_at IS NULL"),
        {"id": media_id, "now": now},
    )


async def ready_variants(db: AsyncSession, media_id: UUID) -> list[dict[str, Any]] | None:
    """The variants of a ready, not deleted media; None otherwise."""
    return await db.scalar(
        text(
            "SELECT variants FROM media WHERE id = :id AND status = 'ready' AND deleted_at IS NULL"
        ),
        {"id": media_id},
    )


async def ready_variants_of(
    db: AsyncSession, media_ids: Sequence[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    """The variants of each ready, not deleted media among `media_ids`, in one query."""
    rows = await db.execute(
        text(
            "SELECT id, variants FROM media WHERE id = ANY(:ids) AND status = 'ready'"
            " AND deleted_at IS NULL AND quarantined_at IS NULL"
        ),
        {"ids": list(media_ids)},
    )
    return {row.id: row.variants for row in rows}


async def erase_media(db: AsyncSession, user_id: UUID) -> None:
    """GDPR eraser (within the account's erasure): every photo hidden at once, what it says of
    the person cleared; files and rows go with the next purge."""
    await db.execute(
        text(
            "UPDATE media SET deleted_at = coalesce(deleted_at, now()), captured_at = NULL,"
            " moderation = '{}' WHERE owner_id = :u"
        ),
        {"u": user_id},
    )


def _rowcount(result: Any) -> int:
    return result.rowcount


async def mark_detached(db: AsyncSession, media_ids: Sequence[UUID], at: datetime) -> None:
    await db.execute(
        text("UPDATE media SET detached_at = :at WHERE id = ANY(:ids)"),
        {"at": at, "ids": list(media_ids)},
    )


# Photos nobody uses: an avatar nobody chose, a listing photo in no listing (never attached, or
# taken off a draft: its 24 hours count from then). A refusal follows its own retention
# (`refused_before`). Each: the photos to lock, then the update, which checks again with a new
# snapshot.
_UNUSED = (
    (
        text(
            "SELECT id FROM media WHERE purpose = 'avatar' AND deleted_at IS NULL"
            " AND status <> 'rejected' AND created_at < :abandoned_before"
            " AND NOT EXISTS (SELECT 1 FROM users u WHERE u.avatar_media_id = media.id)"
            " FOR NO KEY UPDATE SKIP LOCKED"
        ),
        text(
            "UPDATE media m SET deleted_at = :now WHERE m.id = ANY(:ids)"
            " AND NOT EXISTS (SELECT 1 FROM users u WHERE u.avatar_media_id = m.id)"
        ),
    ),
    (
        text(
            "SELECT id FROM media WHERE purpose = 'listing' AND deleted_at IS NULL"
            " AND status <> 'rejected' AND GREATEST(created_at, detached_at) < :abandoned_before"
            " AND NOT EXISTS (SELECT 1 FROM listing_media lm WHERE lm.media_id = media.id)"
            " FOR NO KEY UPDATE SKIP LOCKED"
        ),
        text(
            "UPDATE media m SET deleted_at = :now WHERE m.id = ANY(:ids)"
            " AND NOT EXISTS (SELECT 1 FROM listing_media lm WHERE lm.media_id = m.id)"
        ),
    ),
)


async def mark_for_purge(
    db: AsyncSession, *, now: datetime, abandoned_before: datetime, refused_before: datetime
) -> int:
    """Purge, step 1: uploads never completed, photos nobody used (avatar never chosen, listing
    photo in no listing) and old refusals are marked deleted, so a worker or a member can no
    longer make them ready, an avatar or a listing's.

    Unused photos are locked first, skipping the ones a member is choosing or attaching right
    now (`check_avatar` and `check_listing_photos` hold them FOR SHARE, which conflicts with
    FOR NO KEY UPDATE); the second statement, with a new snapshot, sees the photos used up to
    the lock."""
    params = {"now": now, "abandoned_before": abandoned_before, "refused_before": refused_before}
    marked = 0
    for query in (
        "UPDATE media SET deleted_at = :now WHERE deleted_at IS NULL"
        " AND status = 'uploading' AND created_at < :abandoned_before",
        "UPDATE media SET deleted_at = :now WHERE deleted_at IS NULL"
        " AND status = 'rejected' AND created_at < :refused_before",
    ):
        result = await db.execute(text(query), params)
        marked += _rowcount(result)
    for lock, update in _UNUSED:
        unused: list[UUID] = list(await db.scalars(lock, {"abandoned_before": abandoned_before}))
        if unused:
            result = await db.execute(update, {"now": now, "ids": unused})
            marked += _rowcount(result)
    return marked


_FILES_TO_DELETE = text(
    "SELECT id, storage_key, variants, quarantined_at FROM media"
    " WHERE deleted_at IS NOT NULL AND files_deleted_at IS NULL"
    " AND files_purge_failed_at IS NULL"
    " AND (CAST(:after AS uuid) IS NULL OR id > :after) ORDER BY id LIMIT :limit"
)
_FILES_TO_RETRY = text(
    "SELECT id, storage_key, variants, quarantined_at FROM media"
    " WHERE deleted_at IS NOT NULL AND files_deleted_at IS NULL"
    " AND files_purge_failed_at < :failed_before"
    " AND (CAST(:after AS uuid) IS NULL OR id > :after) ORDER BY id LIMIT :limit"
)


async def files_to_delete(
    db: AsyncSession, *, retry_failed_before: datetime | None, after: UUID | None, limit: int
) -> list[Row[Any]]:
    """Purge, step 2: deleted media whose files are still stored, in id order from `after`:
    (id, storage_key, variants). Deleted means final: their variants no longer change.

    The ones that never failed first; with `retry_failed_before`, the ones that failed
    before then, so a file that keeps failing never holds the others back."""
    if retry_failed_before is None:
        query, params = _FILES_TO_DELETE, {"after": after, "limit": limit}
    else:
        query = _FILES_TO_RETRY
        params = {"after": after, "limit": limit, "failed_before": retry_failed_before}
    return list(await db.execute(query, params))


async def mark_files_purge_failed(db: AsyncSession, media_id: UUID, now: datetime) -> None:
    await db.execute(
        text("UPDATE media SET files_purge_failed_at = :now WHERE id = :id"),
        {"id": media_id, "now": now},
    )


async def mark_files_deleted(db: AsyncSession, media_id: UUID, now: datetime) -> None:
    await db.execute(
        text(
            "UPDATE media SET files_deleted_at = :now WHERE id = :id AND files_deleted_at IS NULL"
        ),
        {"id": media_id, "now": now},
    )


async def delete_purged_rows(db: AsyncSession, *, deleted_before: datetime) -> int:
    """Purge, step 3: rows whose files are gone, once the retention has passed, at once for
    an erased account or a media that never became a photo. An avatar pointing at one is
    cleared (ON DELETE SET NULL)."""
    result = await db.execute(
        text(
            "DELETE FROM media m WHERE m.files_deleted_at IS NOT NULL"
            " AND (m.deleted_at < :deleted_before OR m.status <> 'ready'"
            "      OR EXISTS (SELECT 1 FROM users u WHERE u.id = m.owner_id"
            "                 AND u.status = 'deleted'))"
        ),
        {"deleted_before": deleted_before},
    )
    return _rowcount(result)


async def files_overdue(db: AsyncSession, *, deleted_before: datetime) -> int:
    """Media deleted before `deleted_before` (withdrawn photo, erased account) whose files are
    still stored."""
    return (
        await db.scalar(
            text(
                "SELECT count(*) FROM media WHERE deleted_at < :before AND files_deleted_at IS NULL"
            ),
            {"before": deleted_before},
        )
        or 0
    )


async def ready_moderation_of(
    db: AsyncSession, media_ids: Sequence[UUID]
) -> dict[UUID, dict[str, Any]]:
    """The `moderation` of each photo still ready among `media_ids`, by id."""
    if not media_ids:
        return {}
    rows = await db.execute(
        text(
            "SELECT id, moderation FROM media WHERE id = ANY(:ids) AND status = 'ready'"
            " AND deleted_at IS NULL"
        ),
        {"ids": list(media_ids)},
    )
    return {row.id: row.moderation for row in rows}


async def quarantine(db: AsyncSession, media_ids: Sequence[UUID], now: datetime) -> None:
    """Plan Q40, P2-T05c1b: photos of a listing removed by the moderation, never shown again."""
    await db.execute(
        text(
            "UPDATE media SET quarantined_at = :now WHERE id = ANY(:ids)"
            " AND quarantined_at IS NULL AND deleted_at IS NULL"
        ),
        {"ids": list(media_ids), "now": now},
    )


_TO_MOVE = text(
    "SELECT id, variants FROM media WHERE quarantined_at IS NOT NULL"
    " AND quarantine_moved_at IS NULL AND deleted_at IS NULL"
    " AND (CAST(:after AS uuid) IS NULL OR id > :after) ORDER BY id LIMIT :limit"
)
_QUARANTINE_OVERDUE = text(
    "SELECT count(*) FROM media WHERE quarantined_at IS NOT NULL"
    " AND quarantine_moved_at IS NULL AND deleted_at IS NULL AND quarantined_at < :before"
)


async def quarantined_to_move(
    db: AsyncSession, *, after: UUID | None, limit: int
) -> list[Row[Any]]:
    """Quarantined photos whose variants are still public: (id, variants), after `after`."""
    return list(await db.execute(_TO_MOVE, {"after": after, "limit": limit}))


async def quarantine_overdue(db: AsyncSession, *, quarantined_before: datetime) -> int:
    return int(await db.scalar(_QUARANTINE_OVERDUE, {"before": quarantined_before}) or 0)


async def mark_quarantine_moved(db: AsyncSession, media_id: UUID, now: datetime) -> None:
    """Only while still quarantined and kept (a photo restored or deleted meanwhile stays so)."""
    await db.execute(
        text(
            "UPDATE media SET quarantine_moved_at = :now WHERE id = :id"
            " AND quarantined_at IS NOT NULL AND deleted_at IS NULL"
        ),
        {"id": media_id, "now": now},
    )


async def set_caption(db: AsyncSession, media_id: UUID, caption: str) -> None:
    await db.execute(
        text(
            "UPDATE media SET moderation = moderation"
            " || jsonb_build_object('caption', CAST(:c AS text)) WHERE id = :id"
        ),
        {"id": media_id, "c": caption},
    )
