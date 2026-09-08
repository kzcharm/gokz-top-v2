"""add polls

Revision ID: 3b7c1f0a9d12
Revises: 2f70a5a03050
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "3b7c1f0a9d12"
down_revision = "2f70a5a03050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    poll_status = postgresql.ENUM(
        "active", "closed", name="poll_status", create_type=False
    )
    poll_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "poll",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "title", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=5000), nullable=True
        ),
        sa.Column("status", poll_status, nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_selections", sa.Integer(), nullable=False),
        sa.Column("allow_vote_change", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_poll_status_created_at", "poll", ["status", "created_at"])
    op.create_index("ix_poll_last_activity_at", "poll", ["last_activity_at"])
    op.create_table(
        "poll_option",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("poll_id", sa.Uuid(), nullable=False),
        sa.Column(
            "label", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["poll_id"], ["poll.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_poll_option_poll_position", "poll_option", ["poll_id", "position"]
    )
    op.create_table(
        "poll_vote",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("poll_id", sa.Uuid(), nullable=False),
        sa.Column("user_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("option_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["poll_id"], ["poll.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_steamid64"], ["user.steamid64"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_poll_vote_poll_user",
        "poll_vote",
        ["poll_id", "user_steamid64"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("poll_vote")
    op.drop_index("ix_poll_option_poll_position", table_name="poll_option")
    op.drop_table("poll_option")
    op.drop_index("ix_poll_last_activity_at", table_name="poll")
    op.drop_index("ix_poll_status_created_at", table_name="poll")
    op.drop_table("poll")
    postgresql.ENUM(name="poll_status").drop(op.get_bind(), checkfirst=True)
