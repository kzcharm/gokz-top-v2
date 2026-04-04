"""add player profile views

Revision ID: 18cc548ce8c8
Revises: f360688d2bb8
Create Date: 2026-04-04 16:08:22.291989

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "18cc548ce8c8"
down_revision = "f360688d2bb8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playerprofileview",
        sa.Column("viewer_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("target_steamid64", sa.BigInteger(), nullable=False),
        sa.Column("view_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["target_steamid64"],
            ["player.steamid64"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["viewer_steamid64"],
            ["user.steamid64"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("viewer_steamid64", "target_steamid64", "view_date"),
    )
    op.create_index(
        "ix_player_profile_view_target_view_date",
        "playerprofileview",
        ["target_steamid64", "view_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_profile_view_target_view_date",
        table_name="playerprofileview",
    )
    op.drop_table("playerprofileview")
