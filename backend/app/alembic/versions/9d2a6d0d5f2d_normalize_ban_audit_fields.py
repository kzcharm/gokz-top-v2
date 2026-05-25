"""normalize ban audit fields

Revision ID: 9d2a6d0d5f2d
Revises: 76bec12252fc
Create Date: 2026-05-25 18:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "9d2a6d0d5f2d"
down_revision = "76bec12252fc"
branch_labels = None
depends_on = None


def _rename_column(table_name: str, old_name: str, new_name: str) -> None:
    op.alter_column(table_name, old_name, new_column_name=new_name)


def _rename_index(old_name: str, new_name: str) -> None:
    op.execute(sa.text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


def upgrade() -> None:
    _rename_column("ban", "expires_on", "expires_at")
    _rename_index("ix_ban_steamid64_expires_on", "ix_ban_steamid64_expires_at")

    _rename_column("ban", "updated_by_id", "updated_by_steamid64")
    op.alter_column(
        "ban",
        "updated_by_steamid64",
        existing_type=sa.String(length=32),
        type_=sa.BigInteger(),
        postgresql_using="""
        CASE
            WHEN updated_by_steamid64 IS NULL OR BTRIM(updated_by_steamid64) = '' THEN NULL
            WHEN BTRIM(updated_by_steamid64) ~ '^[0-9]+$' THEN CAST(BTRIM(updated_by_steamid64) AS BIGINT)
            ELSE NULL
        END
        """,
        existing_nullable=True,
    )
    op.execute(sa.text("UPDATE ban SET updated_by_steamid64 = NULL"))


def downgrade() -> None:
    op.alter_column(
        "ban",
        "updated_by_steamid64",
        existing_type=sa.BigInteger(),
        type_=sa.String(length=32),
        postgresql_using="""
        CASE
            WHEN updated_by_steamid64 IS NULL THEN NULL
            ELSE CAST(updated_by_steamid64 AS TEXT)
        END
        """,
        existing_nullable=True,
    )
    _rename_column("ban", "updated_by_steamid64", "updated_by_id")

    _rename_index("ix_ban_steamid64_expires_at", "ix_ban_steamid64_expires_on")
    _rename_column("ban", "expires_at", "expires_on")
