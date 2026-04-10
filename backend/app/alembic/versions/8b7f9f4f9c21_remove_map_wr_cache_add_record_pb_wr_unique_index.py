"""remove map wr cache add record pb wr unique index

Revision ID: 8b7f9f4f9c21
Revises: 84d85ac0c3bc
Create Date: 2026-04-10 11:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "8b7f9f4f9c21"
down_revision = "84d85ac0c3bc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS cache.ix_cache_map_wrs_record_uuid")
    op.execute("DROP INDEX IF EXISTS cache.ix_cache_map_wrs_map_scope")
    op.execute("DROP TABLE IF EXISTS cache.map_wrs")
    op.execute(
        """
        WITH ranked_wrs AS (
            SELECT
                scope,
                course_id,
                steamid64,
                is_pro_only,
                ROW_NUMBER() OVER (
                    PARTITION BY scope, course_id, is_pro_only
                    ORDER BY time_ms ASC, record_uuid ASC
                ) AS wr_rank
            FROM record_pb
            WHERE points = 1000
        )
        UPDATE record_pb AS rp
        SET points = 999
        FROM ranked_wrs AS rw
        WHERE rp.scope = rw.scope
          AND rp.course_id = rw.course_id
          AND rp.steamid64 = rw.steamid64
          AND rp.is_pro_only = rw.is_pro_only
          AND rw.wr_rank > 1
        """
    )
    op.create_index(
        "ux_record_pb_wr_scope_course_type",
        "record_pb",
        ["scope", "course_id", "is_pro_only"],
        unique=True,
        postgresql_where=sa.text("points = 1000"),
    )


def downgrade() -> None:
    op.drop_index("ux_record_pb_wr_scope_course_type", table_name="record_pb")
    op.execute("CREATE SCHEMA IF NOT EXISTS cache")

    record_type_enum = postgresql.ENUM("NUB", "PRO", name="record_type")
    record_type_enum.create(op.get_bind(), checkfirst=True)
    record_type_enum_existing = postgresql.ENUM(
        "NUB",
        "PRO",
        name="record_type",
        create_type=False,
    )

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
