"""add map review summary cache

Revision ID: c252f46797b9
Revises: e34188d48951
Create Date: 2026-04-09 13:07:36.816345

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c252f46797b9"
down_revision = "e34188d48951"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cache")
    op.create_table(
        "map_review_summaries",
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("overall_avg", sa.Float(), nullable=False),
        sa.Column("gameplay_avg", sa.Float(), nullable=True),
        sa.Column("visuals_avg", sa.Float(), nullable=True),
        sa.Column("reviews_count", sa.Integer(), nullable=False),
        sa.Column("gameplay_count", sa.Integer(), nullable=False),
        sa.Column("visuals_count", sa.Integer(), nullable=False),
        sa.Column("comments_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("map_id"),
        schema="cache",
    )


def downgrade() -> None:
    op.drop_table("map_review_summaries", schema="cache")
    op.execute("DROP SCHEMA IF EXISTS cache")
