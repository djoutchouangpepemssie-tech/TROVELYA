"""Identity and sign-in tables (docs/CAHIER_DES_CHARGES.md section 7.3, P1-T01a).

Gaps from the spec, recorded in docs/plans/P1-identite-comptes.md:
- E5: `magic_links.purpose` also accepts 'step_up' (step-up by magic link, section 13.2).
- E6: `users.profile_completed_at` (sign-up finished) and `users.erasure_requested_at`
  (GDPR erasure grace period).
- E7: `sessions.country_code` (new device or country alert).
- `users.username` is checked as text: on CITEXT the `~` operator ignores case, which would
  let upper-case usernames through.

Tokens are never stored: only their SHA-256 (`token_hash`).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""

from trovelya.core.migrations.sql import execute_script

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TYPE user_status AS ENUM ('active','restricted','suspended','banned','deleted');

CREATE TABLE users (
  id                   UUID PRIMARY KEY,
  email                CITEXT NOT NULL UNIQUE,
  email_verified_at    TIMESTAMPTZ,
  phone_e164           TEXT UNIQUE,
  phone_verified_at    TIMESTAMPTZ,
  username             CITEXT NOT NULL UNIQUE
                         CHECK (username::text ~ '^[a-z0-9_.]{3,30}$'),
  display_name         TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 60),
  avatar_media_id      UUID,
  bio                  TEXT CHECK (char_length(bio) <= 500),
  locale               TEXT NOT NULL DEFAULT 'fr-FR',
  timezone             TEXT NOT NULL DEFAULT 'Europe/Paris',
  country_code         CHAR(2) NOT NULL DEFAULT 'FR',
  status               user_status NOT NULL DEFAULT 'active',
  visibility_factor    NUMERIC(3,2) NOT NULL DEFAULT 1.00
                         CHECK (visibility_factor BETWEEN 0 AND 1),
  is_staff             BOOLEAN NOT NULL DEFAULT false,
  birth_year           SMALLINT,
  marketing_opt_in     BOOLEAN NOT NULL DEFAULT false,
  last_seen_at         TIMESTAMPTZ,
  profile_completed_at TIMESTAMPTZ,
  erasure_requested_at TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at           TIMESTAMPTZ
);
CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX users_erasure_requested_idx ON users (erasure_requested_at)
  WHERE erasure_requested_at IS NOT NULL;

CREATE TABLE auth_identities (
  id               UUID PRIMARY KEY,
  user_id          UUID NOT NULL REFERENCES users(id),
  provider         TEXT NOT NULL CHECK (provider IN ('google','apple')),
  provider_subject TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_subject)
);
CREATE INDEX auth_identities_user_idx ON auth_identities (user_id);

CREATE TABLE passkeys (
  id            UUID PRIMARY KEY,
  user_id       UUID NOT NULL REFERENCES users(id),
  credential_id BYTEA NOT NULL UNIQUE,
  public_key    BYTEA NOT NULL,
  sign_count    BIGINT NOT NULL DEFAULT 0,
  transports    TEXT[],
  name          TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at  TIMESTAMPTZ
);
CREATE INDEX passkeys_user_idx ON passkeys (user_id);

CREATE TABLE magic_links (
  id          UUID PRIMARY KEY,
  email       CITEXT NOT NULL,
  token_hash  BYTEA NOT NULL UNIQUE,
  purpose     TEXT NOT NULL
                CHECK (purpose IN ('login','verify_email','change_email','step_up')),
  expires_at  TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  ip          INET,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX magic_links_email_idx ON magic_links (email, created_at);
CREATE INDEX magic_links_expires_idx ON magic_links (expires_at);

CREATE TABLE sessions (
  id           UUID PRIMARY KEY,
  user_id      UUID NOT NULL REFERENCES users(id),
  token_hash   BYTEA NOT NULL UNIQUE,
  kind         TEXT NOT NULL CHECK (kind IN ('web','mobile','admin')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  revoked_at   TIMESTAMPTZ,
  ip           INET,
  user_agent   TEXT,
  device_label TEXT,
  country_code CHAR(2) CHECK (country_code ~ '^[A-Z]{2}$'),
  mfa_at       TIMESTAMPTZ
);
CREATE INDEX sessions_user_idx ON sessions (user_id) WHERE revoked_at IS NULL;
"""

DOWNGRADE = r"""
DROP TABLE sessions;
DROP TABLE magic_links;
DROP TABLE passkeys;
DROP TABLE auth_identities;
DROP TABLE users;
DROP TYPE user_status;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
