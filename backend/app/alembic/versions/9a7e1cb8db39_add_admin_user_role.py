"""Add admin user role

Revision ID: 9a7e1cb8db39
Revises: bff1baabf044
Create Date: 2026-05-25 12:00:00.000000

"""

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9a7e1cb8db39"
down_revision = "bff1baabf044"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'admin'")


def downgrade():
    bind = op.get_bind()
    user_role = postgresql.ENUM(
        "superuser",
        "map_admin",
        "server_owner",
        name="user_role",
    )

    op.execute(
        """
        UPDATE "user"
        SET roles = array_remove(roles, 'admin'::user_role)
        """
    )
    op.execute("ALTER TYPE user_role RENAME TO user_role_old")
    user_role.create(bind, checkfirst=False)
    op.execute(
        """
        ALTER TABLE "user"
        ALTER COLUMN roles
        TYPE user_role[]
        USING (roles::text[]::user_role[])
        """
    )
    op.execute("DROP TYPE user_role_old")
