"""Quarantine of the photos of a listing removed by the moderation (P2-T05c1b, plan Q40): never
shown again from `quarantined_at`; their variants moved to a private copy by the hourly purge
(`quarantine_moved_at`), kept for the appeal until the listing's retention deletes them.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE media
  ADD COLUMN quarantined_at TIMESTAMPTZ,
  ADD COLUMN quarantine_moved_at TIMESTAMPTZ,
  ADD CONSTRAINT media_quarantine_moved_after
    CHECK (quarantine_moved_at IS NULL OR quarantined_at IS NOT NULL);
-- What the hourly purge still has to move to the private bucket.
CREATE INDEX media_quarantine_to_move_idx ON media (id)
  WHERE quarantined_at IS NOT NULL AND quarantine_moved_at IS NULL AND deleted_at IS NULL;
"""

DOWNGRADE = r"""
DROP INDEX media_quarantine_to_move_idx;
ALTER TABLE media
  DROP CONSTRAINT media_quarantine_moved_after,
  DROP COLUMN quarantine_moved_at,
  DROP COLUMN quarantined_at;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
