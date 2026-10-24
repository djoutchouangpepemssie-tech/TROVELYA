"""Profile completion and optimistic locking (P1-T05a).

Additions to the spec, recorded in docs/plans/P1-identite-comptes.md (E15, E16):
- E15: `users.version`, incremented by every update of the row, is the `If-Match` value of
  `PATCH /v1/me` (section 11.1, optimistic locking).
- E16: `consents.purpose` also accepts 'terms': each accepted version of the terms of use is
  recorded with its `policy_version` (section 14, legal documents).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24
"""

from trovelya.core.migrations.sql import execute_script

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE users ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1);

CREATE FUNCTION bump_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.version := OLD.version + 1;
  RETURN NEW;
END;
$$;
CREATE TRIGGER users_bump_version BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION bump_version();

ALTER TABLE consents DROP CONSTRAINT consents_purpose_check;
ALTER TABLE consents ADD CONSTRAINT consents_purpose_check
  CHECK (purpose IN ('analytics','marketing_email','personalised_ads','location','terms'));
"""

DOWNGRADE = r"""
DELETE FROM consents WHERE purpose = 'terms';
ALTER TABLE consents DROP CONSTRAINT consents_purpose_check;
ALTER TABLE consents ADD CONSTRAINT consents_purpose_check
  CHECK (purpose IN ('analytics','marketing_email','personalised_ads','location'));
DROP TRIGGER users_bump_version ON users;
DROP FUNCTION bump_version();
ALTER TABLE users DROP COLUMN version;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
