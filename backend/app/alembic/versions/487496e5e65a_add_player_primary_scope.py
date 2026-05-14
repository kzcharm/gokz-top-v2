"""add player primary scope

Revision ID: 487496e5e65a
Revises: b1eb2523abfa
Create Date: 2026-05-14 14:40:53.956811

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "487496e5e65a"
down_revision = "b1eb2523abfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player",
        sa.Column(
            "primary_scope",
            sa.Enum("OVR", "KZT", "SKZ", "VNL", name="mode_scope"),
            nullable=False,
            server_default="OVR",
        ),
    )


def downgrade() -> None:
    op.drop_column("player", "primary_scope")
