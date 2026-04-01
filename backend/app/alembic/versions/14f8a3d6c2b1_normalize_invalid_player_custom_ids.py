"""normalize invalid player custom ids

Revision ID: 14f8a3d6c2b1
Revises: fceabf6eecdf
Create Date: 2026-04-01 10:30:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "14f8a3d6c2b1"
down_revision = "fceabf6eecdf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE player
        SET custom_id = CASE
            WHEN custom_id IS NULL THEN NULL
            WHEN length(btrim(custom_id)) = 0 THEN NULL
            ELSE lower(btrim(custom_id))
        END
    """)
    op.execute("""
        UPDATE player
        SET custom_id = NULL
        WHERE custom_id IS NOT NULL
          AND (
            length(custom_id) > 25
            OR custom_id !~ '^[a-z0-9_-]*[a-z][a-z0-9_-]*$'
          )
    """)


def downgrade() -> None:
    pass
