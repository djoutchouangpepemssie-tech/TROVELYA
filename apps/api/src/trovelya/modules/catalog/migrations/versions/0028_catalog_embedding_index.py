"""HNSW index of the listings' embeddings, cosine distance (P2-T11, ADR-0020): the similar
listings (P2-T10) are the nearest active ones, found without scanning every vector.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE INDEX listings_embedding_hnsw_idx ON listings USING hnsw (embedding vector_cosine_ops)
  WHERE status = 'active' AND embedding IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX listings_embedding_hnsw_idx;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
