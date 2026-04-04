"""rename playerprofileview to snake case

Revision ID: 20a1b6f4f8a2
Revises: 18cc548ce8c8
Create Date: 2026-04-04 16:25:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20a1b6f4f8a2"
down_revision = "18cc548ce8c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("playerprofileview", "player_profile_view")


def downgrade() -> None:
    op.rename_table("player_profile_view", "playerprofileview")
