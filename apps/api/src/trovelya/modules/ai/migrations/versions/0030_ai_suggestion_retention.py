"""Retention of the AI suggestions' log (plan P2 Q46): 365 days after the call, then the daily
purge erases it; the index on `created_at` serves that purge.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE INDEX ai_listing_suggestions_created_idx ON ai_listing_suggestions (created_at);

INSERT INTO platform_settings (key, value, description) VALUES
  ('retention.ai_suggestion_days', '365',
   'Jours avant d''effacer un appel du journal des suggestions IA (Q46)');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings WHERE key = 'retention.ai_suggestion_days';
DROP INDEX ai_listing_suggestions_created_idx;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
