"""Double-entry ledger (docs/CAHIER_DES_CHARGES.md section 7.8, invariants 10.5).

- Balance per transaction and per currency checked at COMMIT by a deferred constraint
  trigger, so entries can be inserted one by one inside the transaction.
- A transaction needs at least two entries (also checked at COMMIT).
- An entry's currency must be its account's currency.
- Transactions and entries are immutable: a mistake is fixed by a reversing transaction.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""

from trovelya.core.migrations.sql import execute_script

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TYPE ledger_account_type AS ENUM ('asset','liability','revenue','expense','equity');

CREATE TABLE ledger_accounts (
  id            UUID PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,
  type          ledger_account_type NOT NULL,
  currency      CHAR(3) NOT NULL,
  owner_user_id UUID,
  description   TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ledger_accounts_owner_idx ON ledger_accounts (owner_user_id);

CREATE TABLE ledger_transactions (
  id              UUID PRIMARY KEY,
  kind            TEXT NOT NULL,
  reference_type  TEXT NOT NULL,
  reference_id    UUID NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  description     TEXT NOT NULL,
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      TEXT NOT NULL
);
CREATE INDEX ledger_transactions_reference_idx
  ON ledger_transactions (reference_type, reference_id);

CREATE TABLE ledger_entries (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  transaction_id UUID NOT NULL REFERENCES ledger_transactions,
  account_id     UUID NOT NULL REFERENCES ledger_accounts,
  direction      CHAR(1) NOT NULL CHECK (direction IN ('D','C')),
  amount_minor   BIGINT NOT NULL CHECK (amount_minor > 0),
  currency       CHAR(3) NOT NULL
);
CREATE INDEX ledger_entries_account_idx ON ledger_entries (account_id, id);
CREATE INDEX ledger_entries_transaction_idx ON ledger_entries (transaction_id);

CREATE FUNCTION ledger_check_entry_currency() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM ledger_accounts WHERE id = NEW.account_id AND currency = NEW.currency
  ) THEN
    RAISE EXCEPTION 'ledger entry currency % does not match account %',
      NEW.currency, NEW.account_id;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER ledger_entries_currency BEFORE INSERT ON ledger_entries
  FOR EACH ROW EXECUTE FUNCTION ledger_check_entry_currency();

CREATE FUNCTION ledger_check_balance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  unbalanced CHAR(3);
BEGIN
  SELECT currency INTO unbalanced
  FROM ledger_entries
  WHERE transaction_id = NEW.transaction_id
  GROUP BY currency
  HAVING sum(CASE direction WHEN 'D' THEN amount_minor ELSE -amount_minor END) <> 0
  LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION 'ledger transaction % unbalanced in %', NEW.transaction_id, unbalanced;
  END IF;
  RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ledger_entries_balanced
  AFTER INSERT ON ledger_entries DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION ledger_check_balance();

CREATE FUNCTION ledger_check_has_entries() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT count(*) FROM ledger_entries WHERE transaction_id = NEW.id) < 2 THEN
    RAISE EXCEPTION 'ledger transaction % needs at least two entries', NEW.id;
  END IF;
  RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ledger_transactions_has_entries
  AFTER INSERT ON ledger_transactions DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION ledger_check_has_entries();

CREATE FUNCTION ledger_reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'ledger records are immutable: post a reversing transaction instead';
END;
$$;
CREATE TRIGGER ledger_entries_immutable BEFORE UPDATE OR DELETE ON ledger_entries
  FOR EACH ROW EXECUTE FUNCTION ledger_reject_change();
CREATE TRIGGER ledger_entries_no_truncate BEFORE TRUNCATE ON ledger_entries
  FOR EACH STATEMENT EXECUTE FUNCTION ledger_reject_change();
CREATE TRIGGER ledger_transactions_immutable BEFORE UPDATE OR DELETE ON ledger_transactions
  FOR EACH ROW EXECUTE FUNCTION ledger_reject_change();
CREATE TRIGGER ledger_transactions_no_truncate BEFORE TRUNCATE ON ledger_transactions
  FOR EACH STATEMENT EXECUTE FUNCTION ledger_reject_change();

CREATE MATERIALIZED VIEW ledger_balances AS
  SELECT account_id, currency,
         sum(CASE direction WHEN 'D' THEN amount_minor ELSE -amount_minor END)
           AS debit_balance_minor
  FROM ledger_entries GROUP BY account_id, currency;
CREATE UNIQUE INDEX ledger_balances_uniq ON ledger_balances (account_id, currency);
"""

DOWNGRADE = r"""
DROP MATERIALIZED VIEW ledger_balances;
DROP TABLE ledger_entries;
DROP TABLE ledger_transactions;
DROP TABLE ledger_accounts;
DROP FUNCTION ledger_reject_change();
DROP FUNCTION ledger_check_has_entries();
DROP FUNCTION ledger_check_balance();
DROP FUNCTION ledger_check_entry_currency();
DROP TYPE ledger_account_type;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
