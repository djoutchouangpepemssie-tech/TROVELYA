"""What hangs on a listing (section 7.5, P2-T03a2): its photos, other members' favorites and
price watches, its price and status histories.

Additions to the spec, recorded in docs/plans/P2-catalogue-annonces.md:
- `listing_status_history` (E8, E15): every transition with its actor and reason; written only
  by the state machine (P2-T04). A system transition has no actor; any other has one.
- A photo belongs to one listing at most; positions are unique per listing, checked at commit
  so photos can be reordered in one transaction.
- Deleting a listing row (only with an account's erasure) deletes its photo links, favorites,
  price watches and histories. The photos themselves stay for the media purge.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE listing_media (
  listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  media_id   UUID NOT NULL UNIQUE REFERENCES media(id),
  position   SMALLINT NOT NULL CHECK (position >= 0),
  PRIMARY KEY (listing_id, media_id),
  CONSTRAINT listing_media_position_key UNIQUE (listing_id, position) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE favorites (
  user_id    UUID NOT NULL REFERENCES users(id),
  listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, listing_id)
);
CREATE INDEX favorites_listing_idx ON favorites (listing_id);

CREATE TABLE price_watches (
  user_id      UUID NOT NULL REFERENCES users(id),
  listing_id   UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  target_minor BIGINT CHECK (target_minor > 0),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, listing_id)
);
CREATE INDEX price_watches_listing_idx ON price_watches (listing_id);

-- The "price history" tab and the Omnibus check (lowest price over 30 days).
CREATE TABLE listing_price_history (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  listing_id  UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  price_minor BIGINT NOT NULL CHECK (price_minor BETWEEN 100 AND 100000000),
  changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX listing_price_history_listing_idx ON listing_price_history (listing_id, changed_at);

-- Every transition of the state machine (E8): who, why, when.
CREATE TABLE listing_status_history (
  id          UUID PRIMARY KEY,
  listing_id  UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  from_status listing_status,
  to_status   listing_status NOT NULL,
  event       TEXT NOT NULL CHECK (event ~ '^[a-z][a-z_]*$'),
  actor_id    UUID,
  actor_kind  TEXT NOT NULL CHECK (actor_kind IN ('user','staff','system')),
  reason_code TEXT CHECK (reason_code ~ '^[a-z][a-z0-9_]*$'),
  reason_text TEXT CHECK (char_length(reason_text) BETWEEN 1 AND 1000),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT listing_status_history_actor_check
    CHECK ((actor_kind = 'system') = (actor_id IS NULL))
);
CREATE INDEX listing_status_history_listing_idx
  ON listing_status_history (listing_id, created_at);
"""

DOWNGRADE = r"""
DROP TABLE listing_status_history;
DROP TABLE listing_price_history;
DROP TABLE price_watches;
DROP TABLE favorites;
DROP TABLE listing_media;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
