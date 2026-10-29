"""Listing photos in no listing (P2-T03b3c, PII.md): the moment a photo was taken off a draft,
from which the purge counts its 24 hours, and the index of that step of the purge.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- Set when a seller takes the photo off a draft; NULL for a photo never attached.
ALTER TABLE media ADD COLUMN detached_at TIMESTAMPTZ;

-- What the purge marks deleted: listing photos in no listing, 24 hours after the later of the
-- upload and the last time they were taken off a draft (GREATEST ignores NULL).
CREATE INDEX media_listing_idx ON media (GREATEST(created_at, detached_at))
  WHERE purpose = 'listing' AND deleted_at IS NULL AND status <> 'rejected';
"""

DOWNGRADE = r"""
DROP INDEX media_listing_idx;
ALTER TABLE media DROP COLUMN detached_at;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
