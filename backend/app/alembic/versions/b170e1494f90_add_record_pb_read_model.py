"""add record pb read model

Revision ID: b170e1494f90
Revises: 6fe0309dbb94
Create Date: 2026-04-02 17:02:41.284119

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b170e1494f90"
down_revision = "6fe0309dbb94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_course",
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_map_course_map_id_stage",
        "map_course",
        ["map_id", "stage"],
        unique=True,
    )
    op.execute(
        """
        INSERT INTO map_course (map_id, stage)
        SELECT DISTINCT map_id, stage
        FROM record
        ON CONFLICT (map_id, stage) DO NOTHING
        """
    )

    op.create_table(
        "record_pb",
        sa.Column("scope", sa.SmallInteger(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("steamid64", sa.BigInteger(), nullable=False),
        sa.Column("is_pro_only", sa.Boolean(), nullable=False),
        sa.Column("record_uuid", sa.Uuid(), nullable=False),
        sa.Column("time_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "points",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "points >= 1 AND points <= 1000",
            name="ck_record_pb_points_range",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["map_course.id"]),
        sa.ForeignKeyConstraint(["record_uuid"], ["record.uuid"]),
        sa.ForeignKeyConstraint(["steamid64"], ["player.steamid64"]),
        sa.PrimaryKeyConstraint("scope", "course_id", "steamid64", "is_pro_only"),
    )
    op.create_index(
        "ix_record_pb_scope_course_pro_time_uuid",
        "record_pb",
        ["scope", "course_id", "is_pro_only", "time_ms", "record_uuid"],
        unique=False,
    )
    op.create_index(
        "ix_record_pb_player_scope_pro_course_time",
        "record_pb",
        ["steamid64", "scope", "is_pro_only", "course_id", "time_ms"],
        unique=False,
    )
    op.create_index(
        "ix_record_pb_record_uuid_scope_pro",
        "record_pb",
        ["record_uuid", "scope", "is_pro_only"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_record_pb_record_uuid_scope_pro", table_name="record_pb")
    op.drop_index("ix_record_pb_player_scope_pro_course_time", table_name="record_pb")
    op.drop_index("ix_record_pb_scope_course_pro_time_uuid", table_name="record_pb")
    op.drop_table("record_pb")
    op.drop_index("ux_map_course_map_id_stage", table_name="map_course")
    op.drop_table("map_course")
