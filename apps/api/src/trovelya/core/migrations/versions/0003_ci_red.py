"""CI must fail: a migration without downgrade (P0-T13 test PR, never merged)."""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("CREATE TABLE ci_red (id int)")
