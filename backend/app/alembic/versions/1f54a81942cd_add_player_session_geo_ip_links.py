"""add player session geo ip links

Revision ID: 1f54a81942cd
Revises: 7cb5fab61c37
Create Date: 2026-04-30 12:45:26.534248

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision = "1f54a81942cd"
down_revision = "7cb5fab61c37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_session",
        sa.Column(
            "geo_country",
            sqlmodel.sql.sqltypes.AutoString(length=2),
            nullable=True,
        ),
    )
    op.add_column(
        "player_session",
        sa.Column(
            "geo_region",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "player_session",
        sa.Column(
            "geo_city",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_player_session_geo_bucket_connected_at",
        "player_session",
        [
            "geo_country",
            "geo_region",
            "geo_city",
            sa.literal_column("connected_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text(
            "geo_country IS NOT NULL "
            "AND geo_region IS NOT NULL "
            "AND geo_city IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_session_geo_bucket_connected_at",
        table_name="player_session",
        postgresql_where=sa.text(
            "geo_country IS NOT NULL "
            "AND geo_region IS NOT NULL "
            "AND geo_city IS NOT NULL"
        ),
    )
    op.drop_column("player_session", "geo_city")
    op.drop_column("player_session", "geo_region")
    op.drop_column("player_session", "geo_country")
