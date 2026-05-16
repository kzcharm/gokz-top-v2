"""add jumpstat table

Revision ID: 2e2f1828273f
Revises: ff30bfc27fd2
Create Date: 2026-05-16 17:34:02.441008

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2e2f1828273f"
down_revision = "ff30bfc27fd2"
branch_labels = None
depends_on = None


jumpstat_type_enum = postgresql.ENUM(
    "LJ",
    "BH",
    "MBH",
    "WJ",
    "LAJ",
    "LAH",
    "JB",
    "LBH",
    "LWJ",
    "FL",
    "UNK",
    "INV",
    name="jumpstat_type",
)
jumpstat_type_enum_column = postgresql.ENUM(
    "LJ",
    "BH",
    "MBH",
    "WJ",
    "LAJ",
    "LAH",
    "JB",
    "LBH",
    "LWJ",
    "FL",
    "UNK",
    "INV",
    name="jumpstat_type",
    create_type=False,
)
kz_mode_enum_column = postgresql.ENUM(
    "KZT",
    "SKZ",
    "VNL",
    "NKZ",
    name="kz_mode",
    create_type=False,
)


def upgrade() -> None:
    jumpstat_type_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "jumpstat",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("server_group_id", sa.Uuid(), nullable=False),
        sa.Column("mode", kz_mode_enum_column, nullable=False),
        sa.Column("type", jumpstat_type_enum_column, nullable=False),
        sa.Column("distance", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("block", sa.Integer(), nullable=True),
        sa.Column("strafes", sa.Integer(), nullable=False),
        sa.Column("sync_percent", sa.Integer(), nullable=False),
        sa.Column("pre_speed", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("max_speed", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("w_count", sa.Integer(), nullable=False),
        sa.Column("overlap_count", sa.Integer(), nullable=False),
        sa.Column("dead_air_count", sa.Integer(), nullable=False),
        sa.Column("width", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("height", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("airtime_percent", sa.Integer(), nullable=False),
        sa.Column("offset", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("crouched_ticks", sa.Integer(), nullable=False),
        sa.Column("edge", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("deviation", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("strafe_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("jumped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mode"], ["mode.name_short"]),
        sa.ForeignKeyConstraint(
            ["player_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["server_group_id"],
            ["server_group.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_jumpstat_block_distance",
        "jumpstat",
        ["block", sa.literal_column("distance DESC")],
        unique=False,
        postgresql_where=sa.text("block IS NOT NULL"),
    )
    op.create_index(
        "ix_jumpstat_group_jumped_at",
        "jumpstat",
        ["server_group_id", sa.literal_column("jumped_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_jumpstat_player_jumped_at",
        "jumpstat",
        ["player_steamid64", sa.literal_column("jumped_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_jumpstat_type_mode_distance",
        "jumpstat",
        [
            "type",
            "mode",
            sa.literal_column("distance DESC"),
            sa.literal_column("jumped_at DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jumpstat_type_mode_distance", table_name="jumpstat")
    op.drop_index("ix_jumpstat_player_jumped_at", table_name="jumpstat")
    op.drop_index("ix_jumpstat_group_jumped_at", table_name="jumpstat")
    op.drop_index("ix_jumpstat_block_distance", table_name="jumpstat")
    op.drop_table("jumpstat")
    jumpstat_type_enum.drop(op.get_bind(), checkfirst=True)
