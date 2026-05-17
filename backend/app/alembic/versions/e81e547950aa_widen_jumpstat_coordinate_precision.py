"""widen jumpstat coordinate precision

Revision ID: e81e547950aa
Revises: 076eccda93e3
Create Date: 2026-05-17 19:24:03.666007

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e81e547950aa"
down_revision = "076eccda93e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "jumpstat",
        "height",
        existing_type=sa.NUMERIC(precision=8, scale=4),
        type_=sa.Numeric(precision=10, scale=4),
        existing_nullable=False,
    )
    op.alter_column(
        "jumpstat",
        "offset",
        existing_type=sa.NUMERIC(precision=8, scale=4),
        type_=sa.Numeric(precision=10, scale=4),
        existing_nullable=False,
    )
    op.alter_column(
        "jumpstat",
        "edge",
        existing_type=sa.NUMERIC(precision=8, scale=4),
        type_=sa.Numeric(precision=10, scale=4),
        existing_nullable=True,
    )
    op.alter_column(
        "jumpstat",
        "deviation",
        existing_type=sa.NUMERIC(precision=8, scale=4),
        type_=sa.Numeric(precision=10, scale=4),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "jumpstat",
        "deviation",
        existing_type=sa.Numeric(precision=10, scale=4),
        type_=sa.NUMERIC(precision=8, scale=4),
        existing_nullable=True,
    )
    op.alter_column(
        "jumpstat",
        "edge",
        existing_type=sa.Numeric(precision=10, scale=4),
        type_=sa.NUMERIC(precision=8, scale=4),
        existing_nullable=True,
    )
    op.alter_column(
        "jumpstat",
        "offset",
        existing_type=sa.Numeric(precision=10, scale=4),
        type_=sa.NUMERIC(precision=8, scale=4),
        existing_nullable=False,
    )
    op.alter_column(
        "jumpstat",
        "height",
        existing_type=sa.Numeric(precision=10, scale=4),
        type_=sa.NUMERIC(precision=8, scale=4),
        existing_nullable=False,
    )
