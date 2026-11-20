"""Preserve existing users/articles while adding roles and publication state."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('role', sa.String(20), nullable=False, server_default='viewer'))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_check_constraint('ck_users_role', 'users', "role IN ('admin','editor','viewer')")
    # Existing articles remain published; new API writes explicitly select draft/published.
    op.add_column('posts', sa.Column('status', sa.String(20), nullable=False, server_default='published'))
    op.add_column('posts', sa.Column('author_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_posts_author_id', 'posts', 'users', ['author_id'], ['id'])
    op.add_column('posts', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute('UPDATE posts SET updated_at=created_at')
    op.create_check_constraint('ck_posts_status', 'posts', "status IN ('draft','published')")
    op.create_index('ix_posts_status', 'posts', ['status'])
    op.create_index('ix_analytics_events_created_at', 'analytics_events', ['created_at'])


def downgrade():
    op.drop_index('ix_analytics_events_created_at', table_name='analytics_events')
    op.drop_index('ix_posts_status', table_name='posts')
    op.drop_constraint('ck_posts_status', 'posts', type_='check')
    op.drop_column('posts', 'updated_at')
    op.drop_constraint('fk_posts_author_id', 'posts', type_='foreignkey')
    op.drop_column('posts', 'author_id')
    op.drop_column('posts', 'status')
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'role')
