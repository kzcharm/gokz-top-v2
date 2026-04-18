"""drop record_pb time_ms

Revision ID: c463639583ad
Revises: 79409830f127
Create Date: 2026-04-18 17:51:33.496258

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c463639583ad"
down_revision = "79409830f127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_record_pb_player_scope_pro_course_time", table_name="record_pb")
    op.drop_index("ix_record_pb_scope_course_pro_time_uuid", table_name="record_pb")
    op.create_index(
        "ix_record_pb_player_scope_pro_course_record_uuid",
        "record_pb",
        ["steamid64", "scope", "is_pro_only", "course_id", "record_uuid"],
        unique=False,
    )
    op.create_index(
        "ix_record_pb_scope_course_pro_record_uuid",
        "record_pb",
        ["scope", "course_id", "is_pro_only", "record_uuid"],
        unique=False,
    )
    op.drop_column("record_pb", "time_ms")


def downgrade() -> None:
    op.add_column(
        "record_pb",
        sa.Column("time_ms", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE record_pb
        SET time_ms = CAST(ROUND(record.time * 1000, 0) AS BIGINT)
        FROM record
        WHERE record.uuid = record_pb.record_uuid
        """
    )
    op.alter_column("record_pb", "time_ms", nullable=False)
    op.drop_index(
        "ix_record_pb_scope_course_pro_record_uuid",
        table_name="record_pb",
    )
    op.drop_index(
        "ix_record_pb_player_scope_pro_course_record_uuid",
        table_name="record_pb",
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
