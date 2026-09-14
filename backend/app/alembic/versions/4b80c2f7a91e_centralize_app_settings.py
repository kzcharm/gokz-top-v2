"""centralize app settings

Revision ID: 4b80c2f7a91e
Revises: e823894fb2fd
Create Date: 2026-09-14 16:00:00.000000

"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4b80c2f7a91e"
down_revision = "e823894fb2fd"
branch_labels = None
depends_on = None

UPGRADE_QQ_BINDING_SECRET_SQL = """
    INSERT INTO app_setting (key, value, created_at, updated_at)
    SELECT
        'qq_binding_secret',
        jsonb_build_object('encrypted_secret', encrypted_secret),
        created_at,
        updated_at
    FROM qq_binding_secret
"""

DOWNGRADE_QQ_BINDING_SECRET_SQL = """
    INSERT INTO qq_binding_secret (
        id,
        encrypted_secret,
        created_at,
        updated_at
    )
    SELECT
        1,
        value ->> 'encrypted_secret',
        created_at,
        updated_at
    FROM app_setting
    WHERE key = 'qq_binding_secret'
"""


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    app_setting = sa.table(
        "app_setting",
        sa.column("key", sa.Text()),
        sa.column("value", postgresql.JSONB()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        app_setting,
        [
            {
                "key": "community_links",
                "value": {"location": "navbar"},
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.execute(sa.text(UPGRADE_QQ_BINDING_SECRET_SQL))
    op.drop_table("qq_binding_secret")


def downgrade() -> None:
    op.create_table(
        "qq_binding_secret",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text(DOWNGRADE_QQ_BINDING_SECRET_SQL))
    op.drop_table("app_setting")
