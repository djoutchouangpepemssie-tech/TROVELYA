"""Thresholds of the moderation of listing photos (P2-T05b2, section 8.17, plan Q38): a score
of `refuse` or more refuses the listing, of `review` or more sends it to a human.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO platform_settings (key, value, description) VALUES
  ('moderation.image_thresholds', '{"refuse": 0.9, "review": 0.5}',
   'Scores d''une photo (nudité, violence, armes, drogue) : refus dès refuse, revue dès review');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings WHERE key = 'moderation.image_thresholds';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
