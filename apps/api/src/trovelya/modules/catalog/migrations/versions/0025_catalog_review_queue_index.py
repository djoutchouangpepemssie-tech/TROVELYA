"""Index of the staff's review queue (P2-T05c1, plan Q16): the few listings awaiting moderation
among all of them, read without scanning the table. The photos of the listings removed before
the quarantine (0024, plan Q40) are quarantined now: the next purge moves them out of public
view (nothing to undo going down).

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE INDEX listings_pending_review_idx ON listings (id)
  WHERE status = 'pending_review' AND deleted_at IS NULL;
UPDATE media SET quarantined_at = now()
  WHERE quarantined_at IS NULL AND deleted_at IS NULL AND id IN (
    SELECT lm.media_id FROM listing_media lm JOIN listings l ON l.id = lm.listing_id
    WHERE l.status = 'removed');
"""

DOWNGRADE = r"""
DROP INDEX listings_pending_review_idx;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
