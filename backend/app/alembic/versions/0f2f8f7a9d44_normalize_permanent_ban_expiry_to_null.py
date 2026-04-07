"""normalize permanent ban expiry to null

Revision ID: 0f2f8f7a9d44
Revises: dde2b02a20af
Create Date: 2026-04-07 14:45:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0f2f8f7a9d44"
down_revision = "dde2b02a20af"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE ban
            SET expires_on = NULL
            WHERE expires_on >= TIMESTAMPTZ '9999-12-31 23:59:59+00'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE ban
            SET expires_on = TIMESTAMPTZ '9999-12-31 23:59:59+00'
            WHERE expires_on IS NULL
            """
        )
    )
