"""add QQ binding secret settings

Revision ID: 7b95b12b26e0
Revises: c9d7e1f2a3b4
Create Date: 2026-08-24 14:41:57.485819

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7b95b12b26e0"
down_revision = "c9d7e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qq_binding_secret",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("qq_binding_secret")
