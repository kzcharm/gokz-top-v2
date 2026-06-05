"""add map file distribution

Revision ID: b6d7e8f90123
Revises: a5705b4a3358
Create Date: 2026-06-05 13:12:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "b6d7e8f90123"
down_revision = "a5705b4a3358"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "map_file_distribution",
        sa.Column("map_id", sa.BigInteger(), nullable=False),
        sa.Column("map_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("workshop_id", sa.BigInteger(), nullable=True),
        sa.Column("map_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bsp_size", sa.BigInteger(), nullable=True),
        sa.Column("bsp_sha256", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("bsp_r2_key", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("bsp_download_url", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("bz2_size", sa.BigInteger(), nullable=True),
        sa.Column("bz2_r2_key", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("bz2_download_url", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("map_id"),
    )
    op.create_index(
        "ix_map_file_distribution_map_name",
        "map_file_distribution",
        ["map_name"],
        unique=False,
    )
    op.create_index(
        "ix_map_file_distribution_synced_at",
        "map_file_distribution",
        ["synced_at"],
        unique=False,
    )
    op.create_table(
        "map_package_release",
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("package_key", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
        sa.Column("package_url", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("map_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("release_date"),
    )


def downgrade():
    op.drop_table("map_package_release")
    op.drop_index(
        "ix_map_file_distribution_synced_at",
        table_name="map_file_distribution",
    )
    op.drop_index(
        "ix_map_file_distribution_map_name",
        table_name="map_file_distribution",
    )
    op.drop_table("map_file_distribution")
