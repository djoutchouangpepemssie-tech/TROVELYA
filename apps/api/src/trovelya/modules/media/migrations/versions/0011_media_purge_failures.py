"""Purge of media (P2-T02c2b): the last failure to delete a media's files, so a file that
keeps failing is retried after the others instead of holding them back.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE media ADD COLUMN files_purge_failed_at TIMESTAMPTZ;
"""

DOWNGRADE = r"""
ALTER TABLE media DROP COLUMN files_purge_failed_at;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
