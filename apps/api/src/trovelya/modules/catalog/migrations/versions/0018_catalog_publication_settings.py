"""Publication of a listing (P2-T04b, plan Q1, Q15, Q24): the [PARAM] it reads.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO platform_settings (key, value, description) VALUES
  ('listings.max_publications_per_day', '50',
   'Annonces mises en ligne par un vendeur sur 24 heures glissantes (publication,'
   || ' republication, renouvellement)'),
  ('listings.expiry_days', '120',
   'Jours en ligne après la dernière publication, le dernier renouvellement'
   || ' ou la dernière modification');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings
  WHERE key IN ('listings.max_publications_per_day', 'listings.expiry_days');
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
