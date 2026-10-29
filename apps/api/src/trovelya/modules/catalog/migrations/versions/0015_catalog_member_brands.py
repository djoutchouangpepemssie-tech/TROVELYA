"""Brands typed by members (plan P2, Q3 and E19, P2-T03b2b0).

A brand a member types that the catalog does not know is created unverified (Q3). It is free
text nobody moderated: it is suggested to others (`GET /v1/brands`) only once an active
listing carries it, and it is linked to the member who typed it, for the GDPR export and
erasure.
- `origin`: 'seed' for the brands of `seed/brands.yaml`, 'member' for the others.
- `created_by`: the member who typed it; NULL for the seed, and once that member is erased.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-27
"""

from trovelya.core.migrations.sql import execute_script

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE brands
  ADD COLUMN origin TEXT NOT NULL DEFAULT 'seed' CHECK (origin IN ('seed','member')),
  ADD COLUMN created_by UUID REFERENCES users(id),
  ADD CONSTRAINT brands_seed_has_no_author CHECK (origin = 'member' OR created_by IS NULL);
CREATE INDEX brands_created_by_idx ON brands (created_by) WHERE created_by IS NOT NULL;
"""

DOWNGRADE = r"""
ALTER TABLE brands DROP COLUMN created_by, DROP COLUMN origin;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
