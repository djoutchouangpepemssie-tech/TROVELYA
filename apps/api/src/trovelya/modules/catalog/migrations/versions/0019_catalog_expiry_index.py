"""The daily expiry of listings (P2-T04d): its own index, so each batch reads only the active
listings whose time is up instead of the whole table.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE INDEX listings_active_expiry_idx ON listings (expires_at, id)
  WHERE status = 'active' AND deleted_at IS NULL;
"""

DOWNGRADE = r"""
DROP INDEX listings_active_expiry_idx;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
