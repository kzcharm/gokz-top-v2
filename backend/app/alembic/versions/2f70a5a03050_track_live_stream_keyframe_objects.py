"""track live stream keyframe objects

Revision ID: 2f70a5a03050
Revises: 87ad211d8498
Create Date: 2026-08-31 21:15:16.155753

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "2f70a5a03050"
down_revision = "87ad211d8498"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "live_stream_state",
        sa.Column(
            "last_keyframe_r2_key",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=True,
        ),
    )
    op.add_column(
        "live_stream_state",
        sa.Column(
            "last_keyframe_image_sha256",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("live_stream_state", "last_keyframe_image_sha256")
    op.drop_column("live_stream_state", "last_keyframe_r2_key")
