"""Retention of ended listings (P2-T04e, plan Q19, PII.md): the [PARAM] of the daily purge
and the index of the listings it looks at.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO platform_settings (key, value, description) VALUES
  ('retention.deleted_listing_days', '30',
   'Jours avant d''effacer une annonce supprimée par son vendeur'),
  ('retention.ended_listing_days', '365',
   'Jours avant d''effacer une annonce retirée ou expirée, sans republication'),
  ('retention.sold_listing_days', '365',
   'Jours avant d''effacer le contenu d''une annonce vendue (fiche minimale gardée, P4)'),
  ('retention.removed_listing_days', '180',
   'Jours avant d''effacer une annonce retirée par la modération (contestation, DSA art. 20)');

-- What the daily purge looks at: ended or deleted listings only, not the whole table.
CREATE INDEX listings_ended_idx ON listings (id)
  WHERE status IN ('withdrawn', 'expired', 'removed') OR deleted_at IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX listings_ended_idx;
DELETE FROM platform_settings WHERE key IN ('retention.deleted_listing_days',
  'retention.ended_listing_days', 'retention.sold_listing_days',
  'retention.removed_listing_days');
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
