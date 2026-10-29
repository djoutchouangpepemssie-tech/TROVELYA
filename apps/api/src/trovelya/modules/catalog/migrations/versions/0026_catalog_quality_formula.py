"""Points of a listing's quality score (P2-T07, plan Q42): photos (the first, then each up to
six), description (from 20 to 300 characters), optional attributes, brand; 100 in all.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO platform_settings (key, value, description) VALUES
  ('listings.quality_formula',
   '{"photos": {"first": 15, "each": 5, "up_to": 6},
     "description": {"points": 30, "from": 20, "full": 300}, "attributes": 20, "brand": 10}',
   'Points du score de qualité d''une annonce (photos, description, attributs facultatifs,'
   ' marque) : 100 au total');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings WHERE key = 'listings.quality_formula';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
