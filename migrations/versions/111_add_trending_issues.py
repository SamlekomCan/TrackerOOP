"""Add trending_issues table for management-tracked trending issues

Revision ID: 111_add_trending_issues
Revises: 110_add_epic_deadline_followup
Create Date: 2026-07-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '111_add_trending_issues'
down_revision = '110_add_epic_deadline_followup'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'trending_issues' not in existing_tables:
        op.create_table(
            'trending_issues',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('detail', sa.Text(), nullable=True),
            sa.Column('pic_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['pic_id'], ['users.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('idx_trending_issues_name', 'trending_issues', ['name'])
        op.create_index('idx_trending_issues_status', 'trending_issues', ['status'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'trending_issues' in existing_tables:
        op.drop_index('idx_trending_issues_status', table_name='trending_issues')
        op.drop_index('idx_trending_issues_name', table_name='trending_issues')
        op.drop_table('trending_issues')
