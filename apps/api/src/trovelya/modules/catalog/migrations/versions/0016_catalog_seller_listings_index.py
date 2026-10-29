"""The seller's listings, newest first, without a status filter (P2-T03b3b, W10).

`listings_seller_idx` leads with `status`: it serves `?status=` but not the whole list, which
PostgreSQL then read and sorted in full for each page. This index serves the list as the API
walks it, page by page, deleted listings left out.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE INDEX listings_seller_recent_idx ON listings (seller_id, created_at DESC, id DESC)
  WHERE deleted_at IS NULL;
"""

DOWNGRADE = r"""
DROP INDEX listings_seller_recent_idx;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
