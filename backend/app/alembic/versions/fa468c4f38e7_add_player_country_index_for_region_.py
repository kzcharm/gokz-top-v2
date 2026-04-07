"""add player country index for region filters

Revision ID: fa468c4f38e7
Revises: 0f2f8f7a9d44
Create Date: 2026-04-07 18:05:47.983206

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "fa468c4f38e7"
down_revision = "0f2f8f7a9d44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_player_country_steamid64",
        "player",
        ["country", "steamid64"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_country_steamid64", table_name="player")
