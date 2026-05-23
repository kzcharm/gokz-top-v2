"""add map course tier

Revision ID: a33e61ef01d2
Revises: bcdbe65cef2b
Create Date: 2026-05-22 17:05:29.079512

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a33e61ef01d2"
down_revision = "bcdbe65cef2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_course_tier",
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column(
            "mode",
            postgresql.ENUM(
                "KZT",
                "SKZ",
                "VNL",
                "NKZ",
                name="kz_mode",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(length=32), nullable=True),
        sa.CheckConstraint("tier >= 0 AND tier <= 8", name="ck_map_course_tier_range"),
        sa.ForeignKeyConstraint(["course_id"], ["map_course.id"]),
        sa.ForeignKeyConstraint(["mode"], ["mode.name_short"]),
        sa.PrimaryKeyConstraint("course_id", "mode"),
    )
    op.create_index(
        "ix_map_course_tier_course_id",
        "map_course_tier",
        ["course_id"],
        unique=False,
    )
    op.create_index(
        "ix_map_course_tier_mode",
        "map_course_tier",
        ["mode"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            WITH exact_courses AS (
                SELECT DISTINCT record_filter.map_id, record_filter.stage
                FROM record_filter
                JOIN map
                  ON map.id = record_filter.map_id
                WHERE record_filter.map_id > 0
                  AND record_filter.tickrate = 128
            )
            INSERT INTO map_course (map_id, stage)
            SELECT exact_courses.map_id, exact_courses.stage
            FROM exact_courses
            ON CONFLICT (map_id, stage) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            WITH exact_courses AS (
                SELECT DISTINCT record_filter.map_id, record_filter.stage
                FROM record_filter
                JOIN map
                  ON map.id = record_filter.map_id
                WHERE record_filter.map_id > 0
                  AND record_filter.tickrate = 128
            ),
            exact_course_rows AS (
                SELECT map_course.id, map_course.map_id, map_course.stage
                FROM map_course
                JOIN exact_courses
                  ON exact_courses.map_id = map_course.map_id
                 AND exact_courses.stage = map_course.stage
            ),
            all_modes AS (
                SELECT CAST(mode_name AS kz_mode) AS mode
                FROM (VALUES ('KZT'), ('SKZ'), ('VNL'), ('NKZ')) AS mode_values(mode_name)
            )
            INSERT INTO map_course_tier (
                course_id,
                mode,
                tier,
                created_at,
                updated_at,
                updated_by_id
            )
            SELECT
                exact_course_rows.id AS course_id,
                all_modes.mode,
                COALESCE(MIN(NULLIF(record_filter.tier, 0)), 0) AS tier,
                NOW(),
                NOW(),
                'record-filter-backfill'
            FROM exact_course_rows
            CROSS JOIN all_modes
            LEFT JOIN record_filter
              ON record_filter.map_id = exact_course_rows.map_id
             AND record_filter.stage = exact_course_rows.stage
             AND record_filter.tickrate = 128
             AND record_filter.map_id > 0
             AND record_filter.mode = all_modes.mode
            GROUP BY exact_course_rows.id, all_modes.mode
            ON CONFLICT (course_id, mode) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_map_course_tier_mode", table_name="map_course_tier")
    op.drop_index("ix_map_course_tier_course_id", table_name="map_course_tier")
    op.drop_table("map_course_tier")
