"""Initial PostgreSQL schema. Run before starting application workers."""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("users",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("email",sa.String(320),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_users_email","users",["email"],unique=True)
    op.create_table("posts",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("title",sa.String(180),nullable=False),sa.Column("summary",sa.String(500),nullable=False),sa.Column("content",sa.Text(),nullable=False),sa.Column("category",sa.String(60),nullable=False),sa.Column("read_minutes",sa.Integer(),nullable=False),sa.Column("views",sa.BigInteger(),nullable=False),sa.Column("likes",sa.BigInteger(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("analytics_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("event_name",sa.String(80),nullable=False),sa.Column("path",sa.String(500),nullable=False),sa.Column("visitor_id",sa.String(100)),sa.Column("referrer",sa.String(1000)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table("email_codes",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("email",sa.String(320),nullable=False),sa.Column("digest",sa.String(64),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("used",sa.Boolean(),nullable=False),sa.Column("attempts",sa.Integer(),nullable=False))
    op.create_index("ix_email_codes_email","email_codes",["email"])

def downgrade():
    for name in ("email_codes","analytics_events","posts","users"):
        op.drop_table(name)
