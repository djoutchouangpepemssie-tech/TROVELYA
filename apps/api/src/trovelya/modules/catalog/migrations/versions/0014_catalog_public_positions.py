"""One public position per place of a seller (plan P2, Q20 and E18, P2-T03b2a).

The public position of a listing is its real position moved 200 to 500 m. Drawn once per
listing, the listings of one address would scatter around it and their average would come
close to the address. It is therefore drawn once per place of the seller and kept here: every
listing within 50 m of a kept place takes the same offset, whatever address or zone it comes
from (an address and a zone at home, a zone deleted then recreated, a re-typed address). A
place farther than 50 m from all the seller's kept places gets its own draw.

Rows go with the account's erasure; the daily purge of P2-T04 removes those no listing uses.

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
  id              UUID PRIMARY KEY,
  seller_id       UUID NOT NULL REFERENCES users(id),
  location        GEOGRAPHY(Point,4326) NOT NULL,
  location_public GEOGRAPHY(Point,4326) NOT NULL,
  drawn_at        TIMESTAMPTZ NOT NULL
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
