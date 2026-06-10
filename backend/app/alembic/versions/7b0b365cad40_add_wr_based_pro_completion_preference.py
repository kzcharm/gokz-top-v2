"""add wr based pro completion preference

Revision ID: 7b0b365cad40
Revises: 98c0e0a1a14e
Create Date: 2026-06-10 11:36:47.482455

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7b0b365cad40"
down_revision = "98c0e0a1a14e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player",
        sa.Column(
            "use_wr_based_pro_completion",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("player", "use_wr_based_pro_completion")
