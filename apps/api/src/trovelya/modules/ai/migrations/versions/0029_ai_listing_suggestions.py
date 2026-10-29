"""Log of the AI suggestions to list an item (section 7.5, plan P2-T06a, Q45, Q46).

`ai_listing_suggestions` as in 7.5, with one addition recorded in the P2 plan: `outcome`, as
every call to the provider is logged (and counts in the daily cap, Q45), the answered ones and
the others: `pending` while the provider answers, then `ok`, `over_cost` (above
`ai.assist_max_cost_microeur`, never shown), `invalid` (not the schema) or `failed`.
`suggestion` keeps what the provider said, once checked against the schema.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE ai_listing_suggestions (
  id              UUID PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id),
  media_ids       UUID[] NOT NULL CHECK (cardinality(media_ids) BETWEEN 1 AND 4),
  model           TEXT NOT NULL,
  outcome         TEXT NOT NULL DEFAULT 'pending'
                    CHECK (outcome IN ('pending','ok','over_cost','invalid','failed')),
  suggestion      JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(suggestion) = 'object'),
  accepted_fields TEXT[],
  latency_ms      INTEGER CHECK (latency_ms >= 0),
  cost_microeur   INTEGER CHECK (cost_microeur >= 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- The daily cap (Q45) counts a member's calls of the last 24 hours.
CREATE INDEX ai_listing_suggestions_user_idx ON ai_listing_suggestions (user_id, created_at);

INSERT INTO platform_settings (key, value, description) VALUES
  ('ai.assist_per_day', '20', 'Suggestions IA par compte sur 24 heures glissantes (Q45)'),
  ('ai.assist_max_cost_microeur', '20000',
   'Coût maximal d''une suggestion IA, en micro-euros (2 centimes)');
"""

DOWNGRADE = r"""
DELETE FROM platform_settings WHERE key IN ('ai.assist_per_day', 'ai.assist_max_cost_microeur');
DROP TABLE ai_listing_suggestions;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
