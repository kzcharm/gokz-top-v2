"""add map skill analysis

Revision ID: 2b6abad9daad
Revises: d74ff38d65bd
Create Date: 2026-09-18 22:10:31.757872

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2b6abad9daad"
down_revision = "d74ff38d65bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_skill",
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("boxtech", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("strafe", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("bhop", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("climb", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("ladder", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("slide", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("bhop BETWEEN 0 AND 1", name="ck_map_skill_bhop_range"),
        sa.CheckConstraint(
            "boxtech BETWEEN 0 AND 1", name="ck_map_skill_boxtech_range"
        ),
        sa.CheckConstraint("climb BETWEEN 0 AND 1", name="ck_map_skill_climb_range"),
        sa.CheckConstraint("ladder BETWEEN 0 AND 1", name="ck_map_skill_ladder_range"),
        sa.CheckConstraint("slide BETWEEN 0 AND 1", name="ck_map_skill_slide_range"),
        sa.CheckConstraint("strafe BETWEEN 0 AND 1", name="ck_map_skill_strafe_range"),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("map_id"),
    )


def downgrade() -> None:
    op.drop_table("map_skill")
