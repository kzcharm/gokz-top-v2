"""remove items feature

Revision ID: c378f84b491e
Revises: 14f8a3d6c2b1
Create Date: 2026-04-01 17:48:35.638740

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c378f84b491e"
down_revision = "14f8a3d6c2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("item")


def downgrade() -> None:
    op.create_table(
        "item",
        sa.Column("description", sa.VARCHAR(length=255), nullable=True),
        sa.Column("title", sa.VARCHAR(length=255), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("owner_id", sa.BIGINT(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user.steamid64"],
            name=op.f("item_owner_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("item_pkey")),
    )
