"""add general metadata to player social links

Revision ID: c9d7e1f2a3b4
Revises: ('31e6389755c8', 'c2c95b28e9b2')
Create Date: 2026-08-18 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c9d7e1f2a3b4"
down_revision = ("31e6389755c8", "c2c95b28e9b2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_social_link",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("player_social_link", "metadata_json")
