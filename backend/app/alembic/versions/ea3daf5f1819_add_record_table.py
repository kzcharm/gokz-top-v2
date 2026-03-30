"""add record table

Revision ID: ea3daf5f1819
Revises: 4c137ffbfa9f
Create Date: 2026-03-30 18:07:05.935000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "ea3daf5f1819"
down_revision = "4c137ffbfa9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "record",
        sa.Column("id", sa.Integer(), nullable=True),
        sa.Column("steamid64", sa.BigInteger(), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column("mode_id", sa.Integer(), nullable=False),
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("time", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("teleports", sa.Integer(), nullable=False),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        sa.Column("replay_id", sa.Integer(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("uuid", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"]),
        sa.ForeignKeyConstraint(["mode_id"], ["mode.id"]),
        sa.ForeignKeyConstraint(["server_id"], ["server_globalapi.id"]),
        sa.ForeignKeyConstraint(["steamid64"], ["player.steamid64"]),
        sa.PrimaryKeyConstraint("uuid"),
    )
    op.create_index(
        "ix_pb_map_nub",
        "record",
        ["map_id", "stage", "steamid64", "time", "mode_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true AND teleports > 0"),
    )
    op.create_index(
        "ix_pb_map_ovr",
        "record",
        ["map_id", "stage", "steamid64", "time", "mode_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ix_pb_map_pro",
        "record",
        ["map_id", "stage", "steamid64", "time", "mode_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true AND teleports = 0"),
    )
    op.create_index(
        "ix_pb_player_nub",
        "record",
        ["steamid64", "map_id", "stage", "time", "mode_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true AND teleports > 0"),
    )
    op.create_index(
        "ix_pb_player_ovr",
        "record",
        ["steamid64", "map_id", "stage", "time", "mode_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ix_pb_player_pro",
        "record",
        ["steamid64", "map_id", "stage", "time", "mode_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true AND teleports = 0"),
    )
    op.create_index(
        "ix_records_created_on",
        "record",
        [sa.literal_column("created_on DESC")],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ix_records_invalid",
        "record",
        [sa.literal_column("created_on DESC")],
        unique=False,
        postgresql_where=sa.text("is_valid = false"),
    )
    op.create_index(
        "ix_records_server",
        "record",
        ["server_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ix_records_updated_on",
        "record",
        [sa.literal_column("updated_on DESC")],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ux_record_id_not_null",
        "record",
        ["id"],
        unique=True,
        postgresql_where=sa.text("id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_record_id_not_null", table_name="record")
    op.drop_index("ix_records_updated_on", table_name="record")
    op.drop_index("ix_records_server", table_name="record")
    op.drop_index("ix_records_invalid", table_name="record")
    op.drop_index("ix_records_created_on", table_name="record")
    op.drop_index("ix_pb_player_pro", table_name="record")
    op.drop_index("ix_pb_player_ovr", table_name="record")
    op.drop_index("ix_pb_player_nub", table_name="record")
    op.drop_index("ix_pb_map_pro", table_name="record")
    op.drop_index("ix_pb_map_ovr", table_name="record")
    op.drop_index("ix_pb_map_nub", table_name="record")
    op.drop_table("record")
