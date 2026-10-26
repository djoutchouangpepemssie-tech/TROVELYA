"""Purge of media (P2-T02c2, PII.md): retention of deleted media as a business parameter,
the moment a media's files left storage, and one partial index per step of the purge.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO platform_settings (key, value, description) VALUES
  ('retention.deleted_media_days', '30',
   'Jours avant la purge de la ligne d''une photo supprimée (ses fichiers partent dans l''heure)');

-- Set once the original and every variant are gone from storage (ADR-0019: a withdrawn photo
-- leaves storage at once); the row itself stays for the retention above.
ALTER TABLE media ADD COLUMN files_deleted_at TIMESTAMPTZ;
ALTER TABLE media ADD CONSTRAINT media_files_deleted_when_deleted
  CHECK (files_deleted_at IS NULL OR deleted_at IS NOT NULL);

-- What the purge marks deleted: refusals past retention, avatar photos never chosen
-- (uploads never completed use media_purge_idx).
CREATE INDEX media_rejected_idx ON media (created_at)
  WHERE status = 'rejected' AND deleted_at IS NULL;
CREATE INDEX media_avatar_idx ON media (created_at)
  WHERE purpose = 'avatar' AND deleted_at IS NULL;
-- Deleted media whose files are still stored, then rows whose files are gone.
CREATE INDEX media_files_to_delete_idx ON media (id)
  WHERE deleted_at IS NOT NULL AND files_deleted_at IS NULL;
CREATE INDEX media_files_deleted_idx ON media (deleted_at) WHERE files_deleted_at IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX media_files_deleted_idx;
DROP INDEX media_files_to_delete_idx;
DROP INDEX media_avatar_idx;
DROP INDEX media_rejected_idx;
ALTER TABLE media DROP CONSTRAINT media_files_deleted_when_deleted;
ALTER TABLE media DROP COLUMN files_deleted_at;
DELETE FROM platform_settings WHERE key = 'retention.deleted_media_days';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
