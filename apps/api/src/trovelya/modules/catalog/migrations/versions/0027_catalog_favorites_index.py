"""Index of a member's favorites, the latest first (P2-T08, `GET /v1/me/favorites`): a page is
read in order, never by sorting all of a member's favorites.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE INDEX favorites_member_latest_idx ON favorites (user_id, created_at DESC, listing_id DESC);
"""

DOWNGRADE = r"""
DROP INDEX favorites_member_latest_idx;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
