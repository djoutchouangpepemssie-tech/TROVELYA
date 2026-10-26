"""Retention of deleted media as a business parameter (P2-T02c2, PII.md).

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
   'Jours avant la purge d''une photo supprimée (fichiers et ligne) ; sans délai à l''effacement');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings WHERE key = 'retention.deleted_media_days';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
