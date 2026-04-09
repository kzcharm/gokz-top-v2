"""add map wr cache and record type

Revision ID: 29dd29117244
Revises: c252f46797b9
Create Date: 2026-04-09 15:06:41.152032

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "29dd29117244"
down_revision = "c252f46797b9"
branch_labels = None
depends_on = None


record_type_enum = postgresql.ENUM("NUB", "PRO", name="record_type")
record_type_enum_existing = postgresql.ENUM(
    "NUB",
    "PRO",
    name="record_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cache")
    record_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "map_wrs",
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.SmallInteger(), nullable=False),
        sa.Column("type", record_type_enum_existing, nullable=False),
        sa.Column("record_uuid", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["map_id"], ["map.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["record_uuid"], ["record.uuid"]),
        sa.PrimaryKeyConstraint("map_id", "scope", "type"),
        schema="cache",
    )
    op.create_index(
        "ix_cache_map_wrs_map_scope",
        "map_wrs",
        ["map_id", "scope"],
        unique=False,
        schema="cache",
    )
    op.create_index(
        "ix_cache_map_wrs_record_uuid",
        "map_wrs",
        ["record_uuid"],
        unique=False,
        schema="cache",
    )


def downgrade() -> None:
    op.drop_index("ix_cache_map_wrs_record_uuid", table_name="map_wrs", schema="cache")
    op.drop_index("ix_cache_map_wrs_map_scope", table_name="map_wrs", schema="cache")
    op.drop_table("map_wrs", schema="cache")

    record_type_enum.drop(op.get_bind(), checkfirst=True)
