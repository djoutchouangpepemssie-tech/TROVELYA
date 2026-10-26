"""Media files (section 7.5, P2-T02a1, ADR-0019).

Additions to the spec, recorded in docs/plans/P2-catalogue-annonces.md (E11):
- `variants`: the re-encoded files the public sees ([{format, width, height, key, bytes}]).
- `rejection_reason`: why the worker refused a file (type, size, unreadable image).
- `sha256` is known only once the worker has read the file: NULL while uploading or
  processing, required once ready.
- `storage_key` is the random key of the original in the private bucket; the original is
  deleted after processing, the key stays (unique, never reused).
- One upload per row: the row is created with the declared type and size, which the
  presigned URL signs; the worker checks the real ones.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE media (
  id               UUID PRIMARY KEY,
  owner_id         UUID NOT NULL REFERENCES users(id),
  kind             TEXT NOT NULL CHECK (kind IN ('image','video','document','audio')),
  purpose          TEXT NOT NULL CHECK (purpose IN
                     ('listing','avatar','verification_video','dispute_evidence','message','shop')),
  storage_key      TEXT NOT NULL UNIQUE CHECK (storage_key ~ '^[0-9a-f]{32}$'),
  mime_type        TEXT NOT NULL,
  bytes            BIGINT NOT NULL CHECK (bytes > 0),
  width            INTEGER CHECK (width > 0),
  height           INTEGER CHECK (height > 0),
  duration_ms      INTEGER CHECK (duration_ms > 0),
  sha256           BYTEA CHECK (octet_length(sha256) = 32),
  perceptual_hash  BIGINT,
  status           TEXT NOT NULL CHECK (status IN ('uploading','processing','ready','rejected')),
  moderation       JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(moderation) = 'object'),
  captured_at      TIMESTAMPTZ,
  exif_stripped    BOOLEAN NOT NULL DEFAULT false,
  variants         JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(variants) = 'array'),
  rejection_reason TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at       TIMESTAMPTZ,
  CONSTRAINT media_ready_is_complete CHECK (
    status <> 'ready' OR (sha256 IS NOT NULL AND exif_stripped AND variants <> '[]'::jsonb)
  ),
  CONSTRAINT media_rejected_has_reason
    CHECK ((status = 'rejected') = (rejection_reason IS NOT NULL))
);
CREATE INDEX media_owner_idx ON media (owner_id, created_at DESC) WHERE deleted_at IS NULL;
-- Uploads never completed and deleted media, for the purge job (P2-T02c).
CREATE INDEX media_purge_idx ON media (status, created_at)
  WHERE status IN ('uploading','processing');
CREATE INDEX media_deleted_idx ON media (deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX media_sha256_idx ON media (sha256) WHERE sha256 IS NOT NULL;
CREATE TRIGGER media_updated_at BEFORE UPDATE ON media
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE users ADD CONSTRAINT users_avatar_media_id_fkey
  FOREIGN KEY (avatar_media_id) REFERENCES media(id);
"""

DOWNGRADE = r"""
ALTER TABLE users DROP CONSTRAINT users_avatar_media_id_fkey;
DROP TABLE media;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
