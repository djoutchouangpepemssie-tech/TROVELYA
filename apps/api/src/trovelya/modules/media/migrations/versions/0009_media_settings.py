"""Upload limits as business parameters (P2-T02a3, [PARAM] of the P2 plan, section 1).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO platform_settings (key, value, description) VALUES
  ('media.max_image_bytes', '15728640', 'Taille maximale d''une image envoyée, en octets (13.2)'),
  ('media.uploads_per_hour', '30', 'Envois de fichiers par compte et par heure'),
  ('media.uploads_per_day', '200', 'Envois de fichiers par compte et par jour');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings
 WHERE key IN ('media.max_image_bytes', 'media.uploads_per_hour', 'media.uploads_per_day');
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
