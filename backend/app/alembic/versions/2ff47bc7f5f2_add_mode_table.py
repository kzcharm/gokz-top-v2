"""Add mode table

Revision ID: 2ff47bc7f5f2
Revises: f0b3a46c2d91
Create Date: 2026-03-09 21:40:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "2ff47bc7f5f2"
down_revision = "f0b3a46c2d91"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mode",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column(
            "name_short", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False
        ),
        sa.Column("id_plugin", sa.Integer(), nullable=False),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=1023), nullable=False
        ),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column(
            "latest_version_description",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("website", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("repo", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("contact_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_plugin"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("name_short"),
    )


def downgrade():
    op.drop_table("mode")
