"""add live stream keyframe preview

Revision ID: 31c454d04dca
Revises: d8e7d8bab509
Create Date: 2026-05-07 16:54:42.651770

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "31c454d04dca"
down_revision = "d8e7d8bab509"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "live_stream_state",
        sa.Column(
            "last_keyframe_image_url",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("live_stream_state", "last_keyframe_image_url")
