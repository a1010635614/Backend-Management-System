"""Persist upload sessions and attachment metadata for private COS objects."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('assets',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('key',sa.String(500),nullable=False,unique=True),
        sa.Column('filename',sa.String(180),nullable=False),
        sa.Column('content_type',sa.String(100),nullable=False),
        sa.Column('size',sa.BigInteger(),nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))

def downgrade(): op.drop_table('assets')
