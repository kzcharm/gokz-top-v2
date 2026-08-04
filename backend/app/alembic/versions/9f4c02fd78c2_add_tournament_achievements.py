"""add tournament achievements

Revision ID: 9f4c02fd78c2
Revises: 85e0b395b999
Create Date: 2026-08-04 15:11:17.197962

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9f4c02fd78c2"
down_revision = "85e0b395b999"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tournament_level = postgresql.ENUM(
        "S", "A", "B", "C", name="tournament_level", create_type=False
    )
    tournament_level.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "tournament",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column(
            "official_url",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=True,
        ),
        sa.Column("level", tournament_level, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_tournament_date_range"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tournament_ends_on", "tournament", ["ends_on"], unique=False)
    op.create_table(
        "tournament_achievement",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("player_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("placement", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "placement BETWEEN 1 AND 4", name="ck_tournament_achievement_placement"
        ),
        sa.ForeignKeyConstraint(
            ["player_steamid64"], ["player.steamid64"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"], ["tournament.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tournament_achievement_player_steamid64",
        "tournament_achievement",
        ["player_steamid64"],
        unique=False,
    )
    op.create_index(
        "ux_tournament_achievement_tournament_player",
        "tournament_achievement",
        ["tournament_id", "player_steamid64"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_tournament_achievement_tournament_player",
        table_name="tournament_achievement",
    )
    op.drop_index(
        "ix_tournament_achievement_player_steamid64",
        table_name="tournament_achievement",
    )
    op.drop_table("tournament_achievement")
    op.drop_index("ix_tournament_ends_on", table_name="tournament")
    op.drop_table("tournament")
    sa.Enum("S", "A", "B", "C", name="tournament_level").drop(
        op.get_bind(), checkfirst=True
    )
