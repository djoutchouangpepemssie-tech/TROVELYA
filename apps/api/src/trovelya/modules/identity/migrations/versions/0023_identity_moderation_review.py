"""Permission `moderation.review` (P2-T05c1, plan E9, Q16): the listings awaiting moderation
are reviewed by the roles that may already remove a listing.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-29
"""

from trovelya.core.migrations.sql import execute_script

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

UPGRADE = r"""
INSERT INTO permissions (key, description) VALUES
  ('moderation.review', 'Revoir les annonces en attente de modération');

INSERT INTO role_permissions (role_key, permission_key, requires_approval, limit_minor) VALUES
  ('staff_moderator', 'moderation.review', false, NULL),
  ('staff_trust', 'moderation.review', false, NULL),
  ('staff_admin', 'moderation.review', false, NULL),
  ('staff_superadmin', 'moderation.review', false, NULL);
"""

DOWNGRADE = r"""
DELETE FROM role_permissions WHERE permission_key = 'moderation.review';
DELETE FROM permissions WHERE key = 'moderation.review';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
