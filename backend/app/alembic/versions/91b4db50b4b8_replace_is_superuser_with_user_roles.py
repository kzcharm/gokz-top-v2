"""Replace is_superuser with user roles

Revision ID: 91b4db50b4b8
Revises: 229c08a0e5ad
Create Date: 2026-05-04 13:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "91b4db50b4b8"
down_revision = "229c08a0e5ad"
branch_labels = None
depends_on = None


user_role = postgresql.ENUM("superuser", "map_admin", name="user_role")


def upgrade():
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)

    op.add_column(
        "user",
        sa.Column(
            "roles",
            postgresql.ARRAY(user_role),
            nullable=False,
            server_default=sa.text("'{}'::user_role[]"),
        ),
    )
    op.execute(
        """
        UPDATE "user"
        SET roles = CASE
            WHEN is_superuser THEN ARRAY['superuser']::user_role[]
            ELSE ARRAY[]::user_role[]
        END
        """
    )
    op.alter_column("user", "roles", server_default=None)
    op.drop_column("user", "is_superuser")


def downgrade():
    op.add_column(
        "user",
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE "user"
        SET is_superuser = 'superuser' = ANY(roles)
        """
    )
    op.alter_column("user", "is_superuser", server_default=None)
    op.drop_column("user", "roles")

    bind = op.get_bind()
    user_role.drop(bind, checkfirst=True)
