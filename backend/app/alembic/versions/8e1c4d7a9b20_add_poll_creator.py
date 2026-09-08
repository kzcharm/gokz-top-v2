"""store poll creator

Revision ID: 8e1c4d7a9b20
Revises: 3b7c1f0a9d12
"""

import sqlalchemy as sa
from alembic import op

revision = "8e1c4d7a9b20"
down_revision = "3b7c1f0a9d12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("poll", sa.Column("created_by_steamid64", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_poll_created_by_user",
        "poll",
        "user",
        ["created_by_steamid64"],
        ["steamid64"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_poll_created_by_user", "poll", type_="foreignkey")
    op.drop_column("poll", "created_by_steamid64")
