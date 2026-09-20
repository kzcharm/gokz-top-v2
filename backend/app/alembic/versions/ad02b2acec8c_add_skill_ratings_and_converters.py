"""add skill ratings and converters

Revision ID: ad02b2acec8c
Revises: 2b6abad9daad
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ad02b2acec8c"
down_revision = "2b6abad9daad"
branch_labels = None
depends_on = None

SKILLS = ("boxtech", "strafe", "bhop", "climb", "ladder", "slide")


def upgrade() -> None:
    op.create_table(
        "skill_rating_converter",
        sa.Column(
            "scope",
            postgresql.ENUM(
                "OVR", "KZT", "SKZ", "VNL", name="mode_scope", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("skill", sa.Text(), nullable=False),
        sa.Column("anchors", postgresql.JSONB(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scope", "skill"),
    )
    for skill in SKILLS:
        op.add_column(
            "leaderboard_player",
            sa.Column(
                f"rating_{skill}", sa.Integer(), server_default="0", nullable=False
            ),
        )


def downgrade() -> None:
    for skill in reversed(SKILLS):
        op.drop_column("leaderboard_player", f"rating_{skill}")
    op.drop_table("skill_rating_converter")
