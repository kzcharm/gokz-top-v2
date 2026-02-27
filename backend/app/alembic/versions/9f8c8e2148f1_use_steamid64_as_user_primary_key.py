"""Use steamid64 as user primary key

Revision ID: 9f8c8e2148f1
Revises: feb407b55a1c
Create Date: 2026-02-27 22:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "9f8c8e2148f1"
down_revision = "feb407b55a1c"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("item_owner_id_fkey", "item", type_="foreignkey")

    op.add_column("item", sa.Column("owner_steamid64", sa.BigInteger(), nullable=True))
    op.execute(
        """
        UPDATE item
        SET owner_steamid64 = u.steamid64
        FROM "user" AS u
        WHERE item.owner_id = u.id
        """
    )
    op.alter_column("item", "owner_steamid64", nullable=False)
    op.drop_column("item", "owner_id")
    op.alter_column("item", "owner_steamid64", new_column_name="owner_id")

    op.drop_index(op.f("ix_user_steamid64"), table_name="user")
    op.drop_constraint("user_pkey", "user", type_="primary")
    op.create_primary_key("user_pkey", "user", ["steamid64"])
    op.drop_column("user", "id")

    op.create_foreign_key(
        "item_owner_id_fkey",
        "item",
        "user",
        ["owner_id"],
        ["steamid64"],
        ondelete="CASCADE",
    )


def downgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.add_column("user", sa.Column("id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute('UPDATE "user" SET id = uuid_generate_v4() WHERE id IS NULL')
    op.alter_column("user", "id", nullable=False)

    op.drop_constraint("item_owner_id_fkey", "item", type_="foreignkey")

    op.add_column("item", sa.Column("owner_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE item
        SET owner_uuid = u.id
        FROM "user" AS u
        WHERE item.owner_id = u.steamid64
        """
    )
    op.alter_column("item", "owner_uuid", nullable=False)
    op.drop_column("item", "owner_id")
    op.alter_column("item", "owner_uuid", new_column_name="owner_id")

    op.drop_constraint("user_pkey", "user", type_="primary")
    op.create_primary_key("user_pkey", "user", ["id"])
    op.create_index(op.f("ix_user_steamid64"), "user", ["steamid64"], unique=True)

    op.create_foreign_key(
        "item_owner_id_fkey",
        "item",
        "user",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
