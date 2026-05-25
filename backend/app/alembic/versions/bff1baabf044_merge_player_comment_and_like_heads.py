"""merge player comment and like heads

Revision ID: bff1baabf044
Revises: 7340398f7acc, d1fb34ddeb27
Create Date: 2026-05-25 12:54:53.145256

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'bff1baabf044'
down_revision = ('7340398f7acc', 'd1fb34ddeb27')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
