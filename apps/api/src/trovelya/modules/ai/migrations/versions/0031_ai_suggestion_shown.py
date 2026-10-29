"""What the member was shown of an AI suggestion (plan P2 E20, P2-T06a3b).

`suggestion` keeps what the provider said; `shown` what the member saw once the catalogue kept
what it allows. `accepted_fields`, filled when a draft is created from the suggestion, compares
the draft with `shown` (the fields kept as shown).

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE ai_listing_suggestions
  ADD COLUMN shown JSONB CHECK (shown IS NULL OR jsonb_typeof(shown) = 'object');
"""

DOWNGRADE = r"""
ALTER TABLE ai_listing_suggestions DROP COLUMN shown;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
