"""add record pb bucket covering index

Revision ID: 31e6389755c8
Revises: a4f6aeaec889
Create Date: 2026-08-17 18:50:16.689057
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "31e6389755c8"
down_revision = "a4f6aeaec889"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_record_pb_scope_course_type_time_record_uuid", table_name="record_pb")
    op.create_index(
        "ix_record_pb_bucket_points_lookup",
        "record_pb",
        ["scope", "course_id", "type", "time", "record_uuid"],
        unique=False,
        postgresql_include=["steamid64"],
    )


def downgrade() -> None:
    op.drop_index("ix_record_pb_bucket_points_lookup", table_name="record_pb")
    op.create_index(
        "ix_record_pb_scope_course_type_time_record_uuid",
        "record_pb",
        ["scope", "course_id", "type", "time", "record_uuid"],
        unique=False,
    )
