"""SQL of the media module. Only this module's service reads or writes these tables."""

import json
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


async def owned_media(db: AsyncSession, media_id: UUID, owner_id: UUID) -> Row[Any] | None:
    return (
        await db.execute(
            text(
                "SELECT id, purpose, mime_type, status, width, height, variants, rejection_reason"
                " FROM media WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
            ),
            {"id": media_id, "owner": owner_id},
        )
    ).one_or_none()


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


async def mark_for_purge(
    db: AsyncSession, *, now: datetime, abandoned_before: datetime, refused_before: datetime
) -> int:
    """Purge, step 1: uploads never completed and avatar photos never chosen after 24 hours,
    refusals past retention are marked deleted, so a worker can no longer make them ready."""
    params = {"now": now, "abandoned_before": abandoned_before, "refused_before": refused_before}
    marked = 0
    for query in (
        "UPDATE media SET deleted_at = :now WHERE deleted_at IS NULL"
        " AND status = 'uploading' AND created_at < :abandoned_before",
        "UPDATE media SET deleted_at = :now WHERE deleted_at IS NULL"
        " AND status = 'rejected' AND created_at < :refused_before",
        "UPDATE media m SET deleted_at = :now WHERE m.deleted_at IS NULL"
        " AND m.purpose = 'avatar' AND m.created_at < :abandoned_before"
        " AND NOT EXISTS (SELECT 1 FROM users u WHERE u.avatar_media_id = m.id)",
    ):
        marked += _rowcount(await db.execute(text(query), params))
    return marked


async def files_to_delete(db: AsyncSession, *, after: UUID | None, limit: int) -> list[Row[Any]]:
    """Purge, step 2: deleted media whose files are still stored, in id order from `after`:
    (id, storage_key, variants). Deleted means final: their variants no longer change."""
    rows = await db.execute(
        text(
            "SELECT id, storage_key, variants FROM media"
            " WHERE deleted_at IS NOT NULL AND files_deleted_at IS NULL"
            " AND (CAST(:after AS uuid) IS NULL OR id > :after) ORDER BY id LIMIT :limit"
        ),
        {"after": after, "limit": limit},
    )
    return list(rows)


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
