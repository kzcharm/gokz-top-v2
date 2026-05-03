"""add player social links

Revision ID: 229c08a0e5ad
Revises: 1f54a81942cd
Create Date: 2026-05-03 20:43:10.670578

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "229c08a0e5ad"
down_revision = "1f54a81942cd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE player_social_platform AS ENUM (
            'BILIBILI',
            'GITHUB',
            'TWITCH',
            'X',
            'YOUTUBE'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE player_social_link (
            id UUID NOT NULL,
            player_steamid64 BIGINT NOT NULL,
            platform player_social_platform NOT NULL,
            account_identifier VARCHAR(128) NOT NULL,
            verified BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (player_steamid64) REFERENCES player (steamid64)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_player_social_link_player_platform
        ON player_social_link (player_steamid64, platform)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_player_social_link_verified_account
        ON player_social_link (platform, account_identifier)
        WHERE verified = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_player_social_link_verified_account")
    op.execute("DROP INDEX IF EXISTS ux_player_social_link_player_platform")
    op.execute("DROP TABLE IF EXISTS player_social_link")
    op.execute("DROP TYPE IF EXISTS player_social_platform")
