"""add record pb raw rating contribution

Revision ID: c2c95b28e9b2
Revises: b6d7e8f90123
Create Date: 2026-06-05 15:39:55.560031

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c2c95b28e9b2"
down_revision = "b6d7e8f90123"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "record_pb",
        sa.Column(
            "raw_rating_contribution",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_record_pb_raw_rating_contribution_non_negative",
        "record_pb",
        "raw_rating_contribution >= 0",
    )


def downgrade():
    op.drop_constraint(
        "ck_record_pb_raw_rating_contribution_non_negative",
        "record_pb",
        type_="check",
    )
    op.drop_column("record_pb", "raw_rating_contribution")
