"""Anti-circumvention detections (section 7.10, plan P2-T05a, Q12).

`circumvention_detections` as in 7.10, with one addition recorded in the P2 plan: the member's
original text, sealed with AES-256-GCM (`original_sealed`), kept for the review of what was
masked. Never a contact detail in clear: `matched_spans` hold positions, signals and
confidences only. Rows go with the account's erasure.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE circumvention_detections (
  id              UUID PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id),
  source_type     TEXT NOT NULL CHECK (source_type IN
                    ('message','listing','image','live_chat','live_audio','profile')),
  source_id       UUID NOT NULL,
  signals         TEXT[] NOT NULL CHECK (cardinality(signals) > 0 AND signals <@ ARRAY[
                    'phone','email','iban','payment_app','external_link','social_handle',
                    'obfuscated_number','meet_off_app']::text[]),
  matched_spans   JSONB NOT NULL CHECK (jsonb_typeof(matched_spans) = 'array'),
  confidence      NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  action_taken    TEXT NOT NULL
                    CHECK (action_taken IN ('none','masked','warned','blocked','queued')),
  review_status   TEXT NOT NULL DEFAULT 'pending'
                    CHECK (review_status IN
                      ('pending','confirmed','false_positive','auto_confirmed')),
  reviewed_by     UUID,
  reviewed_at     TIMESTAMPTZ,
  original_sealed BYTEA NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX circumvention_detections_user_idx
  ON circumvention_detections (user_id, created_at);
CREATE INDEX circumvention_detections_source_idx
  ON circumvention_detections (source_type, source_id);
-- The review queue (P2-T05c).
CREATE INDEX circumvention_detections_pending_idx ON circumvention_detections (created_at)
  WHERE review_status = 'pending';
"""

DOWNGRADE = r"""
DROP TABLE circumvention_detections;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
