"""Extensions and cross-cutting base tables (docs/CAHIER_DES_CHARGES.md section 7.2).

Tables: platform_settings, feature_flags, outbox_events, processed_events,
idempotency_keys (ADR-0012), audit_log (append-only, SHA-256 chain computed in the
database, ADR-0014).

Extensions are infrastructure provisioned with the image (ADR-0011): upgrade creates
them idempotently, downgrade leaves them in place (other objects, such as the PostGIS
image's own extensions, may depend on them).

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""

from alembic import op

from trovelya.core.migrations.sql import execute_script

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EXTENSIONS = (
    "postgis",
    "vector",
    "pg_trgm",
    "unaccent",
    "citext",
    "btree_gist",
    "ltree",
    "h3",
    "h3_postgis",
)

UPGRADE = r"""
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TABLE platform_settings (
  key          TEXT PRIMARY KEY,
  value        JSONB NOT NULL,
  description  TEXT NOT NULL,
  updated_by   UUID,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER platform_settings_updated_at BEFORE UPDATE ON platform_settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE feature_flags (
  key            TEXT PRIMARY KEY,
  enabled        BOOLEAN NOT NULL DEFAULT false,
  rollout_pct    SMALLINT NOT NULL DEFAULT 0 CHECK (rollout_pct BETWEEN 0 AND 100),
  allow_user_ids UUID[] NOT NULL DEFAULT '{}',
  countries      CHAR(2)[] NOT NULL DEFAULT '{}',
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER feature_flags_updated_at BEFORE UPDATE ON feature_flags
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE outbox_events (
  id             UUID PRIMARY KEY,
  type           TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id   UUID NOT NULL,
  payload        JSONB NOT NULL,
  occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at   TIMESTAMPTZ
);
CREATE INDEX outbox_unpublished_idx ON outbox_events (id) WHERE published_at IS NULL;

CREATE TABLE processed_events (
  consumer     TEXT NOT NULL,
  event_id     UUID NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer, event_id)
);

-- ADR-0012: a nullable user_id cannot be part of a primary key.
CREATE TABLE idempotency_keys (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  key             TEXT NOT NULL,
  user_id         UUID,
  method          TEXT NOT NULL,
  path            TEXT NOT NULL,
  request_hash    TEXT NOT NULL,
  response_status SMALLINT,
  response_body   JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT idempotency_keys_key_user_uniq UNIQUE NULLS NOT DISTINCT (key, user_id)
);
CREATE INDEX idempotency_keys_created_idx ON idempotency_keys (created_at);

CREATE TABLE audit_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_type    TEXT NOT NULL CHECK (actor_type IN ('user','staff','system','api_client')),
  actor_id      UUID,
  approver_id   UUID,
  action        TEXT NOT NULL,
  target_type   TEXT NOT NULL,
  target_id     TEXT NOT NULL,
  reason        TEXT,
  before        JSONB,
  after         JSONB,
  ip            INET,
  user_agent    TEXT,
  request_id    TEXT,
  prev_hash     BYTEA,
  hash          BYTEA NOT NULL
);
CREATE INDEX audit_target_idx ON audit_log (target_type, target_id, occurred_at DESC);
CREATE INDEX audit_actor_idx  ON audit_log (actor_id, occurred_at DESC);

-- Canonical text of a row (ADR-0014). Timestamps are rendered in UTC so the hash does
-- not depend on the session time zone.
CREATE FUNCTION audit_log_canonical(r audit_log) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_build_object(
    'id', r.id,
    'occurred_at', to_char(r.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'actor_type', r.actor_type,
    'actor_id', r.actor_id,
    'approver_id', r.approver_id,
    'action', r.action,
    'target_type', r.target_type,
    'target_id', r.target_id,
    'reason', r.reason,
    'before', r.before,
    'after', r.after,
    'request_id', r.request_id
  )::text
$$;

-- Chain: serialised by a transaction-level advisory lock; the id is (re)assigned under the
-- lock so that id order is chain order even when transactions commit out of order.
-- Requires READ COMMITTED (the application default) so the lookup sees the last commit.
CREATE FUNCTION audit_log_chain() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  last_hash BYTEA;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('audit_log_chain'));
  NEW.id := nextval(pg_get_serial_sequence('audit_log', 'id'));
  SELECT hash INTO last_hash FROM audit_log ORDER BY id DESC LIMIT 1;
  NEW.prev_hash := last_hash;
  NEW.hash := sha256(coalesce(last_hash, ''::bytea)
                     || convert_to(audit_log_canonical(NEW), 'UTF8'));
  RETURN NEW;
END;
$$;
CREATE TRIGGER audit_log_chain BEFORE INSERT ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_chain();

CREATE FUNCTION audit_log_reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$;
CREATE TRIGGER audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_reject_change();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_change();

CREATE FUNCTION audit_verify_chain() RETURNS TABLE (id BIGINT, ok BOOLEAN)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  r audit_log;
  expected_prev BYTEA := NULL;
BEGIN
  FOR r IN SELECT * FROM audit_log ORDER BY audit_log.id LOOP
    id := r.id;
    ok := r.prev_hash IS NOT DISTINCT FROM expected_prev
          AND r.hash = sha256(coalesce(r.prev_hash, ''::bytea)
                              || convert_to(audit_log_canonical(r), 'UTF8'));
    RETURN NEXT;
    expected_prev := r.hash;
  END LOOP;
END;
$$;

-- Application role: may read and append to the audit log, never change it.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN
    CREATE ROLE app_role NOLOGIN;
  END IF;
END
$$;
GRANT SELECT, INSERT ON audit_log TO app_role;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM app_role;
"""

DOWNGRADE = r"""
REVOKE ALL ON audit_log FROM app_role;
DROP FUNCTION audit_verify_chain();
DROP TRIGGER audit_log_chain ON audit_log;
DROP FUNCTION audit_log_chain();
DROP FUNCTION audit_log_canonical(audit_log);
DROP TABLE audit_log;
DROP FUNCTION audit_log_reject_change();
DROP TABLE idempotency_keys;
DROP TABLE processed_events;
DROP TABLE outbox_events;
DROP TABLE feature_flags;
DROP TABLE platform_settings;
DROP FUNCTION set_updated_at();
"""


def upgrade() -> None:
    for name in EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{name}" CASCADE')
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
