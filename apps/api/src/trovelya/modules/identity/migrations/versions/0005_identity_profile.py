"""Profile, social and GDPR tables (section 7.3, P1-T01c).

Additions to the spec, recorded in docs/plans/P1-identite-comptes.md:
- E8: `data_exports` holds the encrypted export archive until object storage exists (P2);
  `data_requests.result_media_id` stays NULL in P1 (ADR-0016).
- One default search zone and one default shipping address per user (partial unique indexes).
- One pending request ('received' or 'processing') per user and kind (review point 5).
- `consents.purpose` limited to the purposes of section 7.3; a consent needs a subject.
- Nobody follows or blocks themselves.
- `follows.followee_shop_id` has no foreign key until shops exist (P10).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24
"""

from trovelya.core.migrations.sql import execute_script

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE addresses (
  id                  UUID PRIMARY KEY,
  user_id             UUID NOT NULL REFERENCES users(id),
  label               TEXT,
  full_name           TEXT NOT NULL,
  line1               TEXT NOT NULL,
  line2               TEXT,
  postal_code         TEXT NOT NULL,
  city                TEXT NOT NULL,
  country_code        CHAR(2) NOT NULL,
  phone_e164          TEXT,
  location            GEOGRAPHY(Point, 4326),
  is_default_shipping BOOLEAN NOT NULL DEFAULT false,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at          TIMESTAMPTZ
);
CREATE TRIGGER addresses_updated_at BEFORE UPDATE ON addresses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX addresses_user_idx ON addresses (user_id) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX addresses_default_shipping_uniq ON addresses (user_id)
  WHERE is_default_shipping AND deleted_at IS NULL;

CREATE TABLE search_zones (
  id         UUID PRIMARY KEY,
  user_id    UUID NOT NULL REFERENCES users(id),
  label      TEXT NOT NULL,
  place_name TEXT NOT NULL,
  center     GEOGRAPHY(Point, 4326) NOT NULL,
  radius_m   INTEGER NOT NULL
               CHECK (radius_m IN (1000, 2000, 5000, 10000, 25000, 50000, 100000)),
  is_default BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER search_zones_updated_at BEFORE UPDATE ON search_zones
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX search_zones_user_idx ON search_zones (user_id);
CREATE UNIQUE INDEX search_zones_default_uniq ON search_zones (user_id) WHERE is_default;

CREATE TABLE user_preferences (
  user_id               UUID PRIMARY KEY REFERENCES users(id),
  interests             TEXT[] NOT NULL DEFAULT '{}',
  sizes                 JSONB NOT NULL DEFAULT '{}',
  budget_max_minor      BIGINT CHECK (budget_max_minor >= 0),
  blocked_brands        TEXT[] NOT NULL DEFAULT '{}',
  feed_discovery_level  SMALLINT NOT NULL DEFAULT 50
                          CHECK (feed_discovery_level BETWEEN 0 AND 100),
  paused_categories     TEXT[] NOT NULL DEFAULT '{}',
  not_now_until         TIMESTAMPTZ,
  personalised_feed     BOOLEAN NOT NULL DEFAULT true,
  notification_settings JSONB NOT NULL DEFAULT '{}',
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER user_preferences_updated_at BEFORE UPDATE ON user_preferences
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE consents (
  id             UUID PRIMARY KEY,
  user_id        UUID REFERENCES users(id),
  anonymous_id   TEXT,
  purpose        TEXT NOT NULL
                   CHECK (purpose IN ('analytics','marketing_email','personalised_ads','location')),
  granted        BOOLEAN NOT NULL,
  policy_version TEXT NOT NULL,
  source         TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(user_id, anonymous_id) >= 1)
);
CREATE INDEX consents_user_idx ON consents (user_id, purpose, created_at);
CREATE INDEX consents_anonymous_idx ON consents (anonymous_id) WHERE anonymous_id IS NOT NULL;

CREATE TABLE follows (
  follower_id      UUID NOT NULL REFERENCES users(id),
  followee_user_id UUID REFERENCES users(id),
  followee_shop_id UUID,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(followee_user_id, followee_shop_id) = 1),
  CONSTRAINT follows_not_self CHECK (followee_user_id IS DISTINCT FROM follower_id)
);
CREATE UNIQUE INDEX follows_uniq
  ON follows (follower_id, coalesce(followee_user_id, followee_shop_id));
CREATE INDEX follows_followee_user_idx ON follows (followee_user_id)
  WHERE followee_user_id IS NOT NULL;

CREATE TABLE blocks (
  blocker_id UUID REFERENCES users(id),
  blocked_id UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (blocker_id, blocked_id),
  CHECK (blocker_id <> blocked_id)
);
CREATE INDEX blocks_blocked_idx ON blocks (blocked_id);

CREATE TABLE data_requests (
  id              UUID PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id),
  kind            TEXT NOT NULL CHECK (kind IN ('export','erasure')),
  status          TEXT NOT NULL CHECK (status IN ('received','processing','completed','refused')),
  result_media_id UUID,
  refusal_reason  TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ
);
CREATE INDEX data_requests_user_idx ON data_requests (user_id, created_at);
CREATE UNIQUE INDEX data_requests_pending_uniq ON data_requests (user_id, kind)
  WHERE status IN ('received','processing');

CREATE TABLE data_exports (
  id              UUID PRIMARY KEY,
  data_request_id UUID NOT NULL UNIQUE REFERENCES data_requests(id),
  ciphertext      BYTEA NOT NULL,
  expires_at      TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX data_exports_expires_idx ON data_exports (expires_at);
"""

DOWNGRADE = r"""
DROP TABLE data_exports;
DROP TABLE data_requests;
DROP TABLE blocks;
DROP TABLE follows;
DROP TABLE consents;
DROP TABLE user_preferences;
DROP TABLE search_zones;
DROP TABLE addresses;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
