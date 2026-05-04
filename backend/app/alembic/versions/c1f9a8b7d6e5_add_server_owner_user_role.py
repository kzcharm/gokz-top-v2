"""Add server_owner user role

Revision ID: c1f9a8b7d6e5
Revises: 91b4db50b4b8
Create Date: 2026-05-04 16:10:00.000000

"""

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c1f9a8b7d6e5"
down_revision = "91b4db50b4b8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'server_owner'")


def downgrade():
    bind = op.get_bind()
    user_role = postgresql.ENUM("superuser", "map_admin", name="user_role")

    op.execute(
        """
        UPDATE "user"
        SET roles = array_remove(roles, 'server_owner'::user_role)
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
