"""One public position per position source (plan P2, Q20, P2-T03b2a).

The public position of a listing is its real position moved 200 to 500 m. Drawn once per
listing, the listings of one address would scatter around it and their average would come
close to the address; it is therefore drawn once per source (an address or a search zone of
the seller), kept here, and shared by every listing of that source. It is drawn again when the
source moves (`location` differs from the source's current position).

Rows go with the account's erasure; the daily purge of P2-T04 removes those of sources that no
longer exist.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-26
"""

from trovelya.core.migrations.sql import execute_script

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE listing_public_positions (
  location_source_id UUID PRIMARY KEY,
  location_source    TEXT NOT NULL CHECK (location_source IN ('address','zone')),
  seller_id          UUID NOT NULL REFERENCES users(id),
  location           GEOGRAPHY(Point,4326) NOT NULL,
  location_public    GEOGRAPHY(Point,4326) NOT NULL,
  drawn_at           TIMESTAMPTZ NOT NULL
);
CREATE INDEX listing_public_positions_seller_idx ON listing_public_positions (seller_id);
"""

DOWNGRADE = r"""
DROP TABLE listing_public_positions;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
