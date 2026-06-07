"""require server group custom id

Revision ID: 8a6d1f0e7c3b
Revises: c2c95b28e9b2
Create Date: 2026-06-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8a6d1f0e7c3b"
down_revision: str | None = "c2c95b28e9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH missing AS (
            SELECT
                id,
                lower(
                    trim(
                        both '-' from regexp_replace(
                            regexp_replace(name, '[^A-Za-z0-9]+', '-', 'g'),
                            '-+',
                            '-',
                            'g'
                        )
                    )
                ) AS base_slug
            FROM server_group
            WHERE custom_id IS NULL OR btrim(custom_id) = ''
        ),
        normalized AS (
            SELECT
                id,
                left(
                    CASE
                        WHEN base_slug = '' THEN 'server-group'
                        ELSE base_slug
                    END,
                    23
                ) AS base_slug
            FROM missing
        ),
        numbered AS (
            SELECT
                id,
                base_slug,
                row_number() OVER (PARTITION BY base_slug ORDER BY id) AS slug_index
            FROM normalized
        )
        UPDATE server_group AS group_row
        SET custom_id =
            CASE
                WHEN numbered.slug_index = 1
                     AND NOT EXISTS (
                        SELECT 1
                        FROM server_group existing
                        WHERE existing.custom_id = numbered.base_slug
                          AND existing.id != numbered.id
                     )
                THEN numbered.base_slug
                ELSE left(numbered.base_slug, 23) || '-' || left(replace(numbered.id::text, '-', ''), 8)
            END
        FROM numbered
        WHERE group_row.id = numbered.id
        """
    )
    op.drop_index("uq_server_group_custom_id_not_null", table_name="server_group")
    op.alter_column("server_group", "custom_id", nullable=False)
    op.create_index(
        "uq_server_group_custom_id",
        "server_group",
        ["custom_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_server_group_custom_id", table_name="server_group")
    op.alter_column("server_group", "custom_id", nullable=True)
    op.create_index(
        "uq_server_group_custom_id_not_null",
        "server_group",
        ["custom_id"],
        unique=True,
        postgresql_where=sa.text("custom_id IS NOT NULL"),
    )
