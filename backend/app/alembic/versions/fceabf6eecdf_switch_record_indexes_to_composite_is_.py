"""switch record indexes to composite is_valid indexes

Revision ID: fceabf6eecdf
Revises: 4dc5933dfa0d
Create Date: 2026-03-31 16:21:17.793789

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fceabf6eecdf"
down_revision = "4dc5933dfa0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "ix_records_created_on",
        table_name="record",
        postgresql_where=sa.text("is_valid = true"),
    )
    op.drop_index(
        "ix_records_invalid",
        table_name="record",
        postgresql_where=sa.text("is_valid = false"),
    )
    op.drop_index(
        "ix_records_server",
        table_name="record",
        postgresql_where=sa.text("is_valid = true"),
    )
    op.drop_index(
        "ix_records_updated_on",
        table_name="record",
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ix_records_is_valid_created_on",
        "record",
        ["is_valid", sa.literal_column("created_on DESC")],
        unique=False,
    )
    op.create_index(
        "ix_records_is_valid_server_id",
        "record",
        ["is_valid", "server_id"],
        unique=False,
    )
    op.create_index(
        "ix_records_is_valid_updated_on",
        "record",
        ["is_valid", sa.literal_column("updated_on DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_records_is_valid_updated_on", table_name="record")
    op.drop_index("ix_records_is_valid_server_id", table_name="record")
    op.drop_index("ix_records_is_valid_created_on", table_name="record")
    op.create_index(
        "ix_records_updated_on",
        "record",
        [sa.literal_column("updated_on DESC")],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ix_records_server",
        "record",
        ["server_id"],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
    op.create_index(
        "ix_records_invalid",
        "record",
        [sa.literal_column("created_on DESC")],
        unique=False,
        postgresql_where=sa.text("is_valid = false"),
    )
    op.create_index(
        "ix_records_created_on",
        "record",
        [sa.literal_column("created_on DESC")],
        unique=False,
        postgresql_where=sa.text("is_valid = true"),
    )
