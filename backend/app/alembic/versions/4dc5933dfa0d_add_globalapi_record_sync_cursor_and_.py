"""add globalapi record sync cursor and points

Revision ID: 4dc5933dfa0d
Revises: ea3daf5f1819
Create Date: 2026-03-30 21:49:36.200517

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "4dc5933dfa0d"
down_revision = "ea3daf5f1819"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "globalapi_sync_state",
        sa.Column("cursor", sa.Integer(), nullable=True),
    )
    op.add_column(
        "record",
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_record_points_range",
        "record",
        "points >= 0 AND points <= 1000",
    )
    op.alter_column("record", "points", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_record_points_range", "record", type_="check")
    op.drop_column("record", "points")
    op.drop_column("globalapi_sync_state", "cursor")
