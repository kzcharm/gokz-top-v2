"""add scheduled task state for record pb points task

Revision ID: 2467d30861e8
Revises: 20a1b6f4f8a2
Create Date: 2026-04-04 17:18:00.534331

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = "2467d30861e8"
down_revision = "20a1b6f4f8a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_task_state",
        sa.Column(
            "task_name",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=False,
        ),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("cursor", sa.Integer(), nullable=True),
        sa.Column("last_processed", sa.Integer(), nullable=False),
        sa.Column("last_created", sa.Integer(), nullable=False),
        sa.Column("last_updated", sa.Integer(), nullable=False),
        sa.Column("last_errors", sa.Integer(), nullable=False),
        sa.Column("last_warnings", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("task_name"),
    )
    op.execute(
        sa.text(
            """
            DELETE FROM globalapi_sync_state
            WHERE task_name = 'record_pb_points'
            """
        )
    )


def downgrade() -> None:
    op.drop_table("scheduled_task_state")
