"""Add Epic/Story hierarchy and link tasks to stories

Revision ID: 108_add_epic_story
Revises: 107_add_task_source
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '108_add_epic_story'
down_revision = '107_add_task_source'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'epics' not in existing_tables:
        op.create_table(
            'epics',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('idx_epics_project_id', 'epics', ['project_id'])
        op.create_index('idx_epics_name', 'epics', ['name'])
        op.create_index('idx_epics_status', 'epics', ['status'])

    if 'stories' not in existing_tables:
        op.create_table(
            'stories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('epic_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['epic_id'], ['epics.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('idx_stories_epic_id', 'stories', ['epic_id'])
        op.create_index('idx_stories_name', 'stories', ['name'])
        op.create_index('idx_stories_status', 'stories', ['status'])

    tasks_cols = {c['name'] for c in inspector.get_columns('tasks')}
    with op.batch_alter_table('tasks') as batch_op:
        if 'story_id' not in tasks_cols:
            batch_op.add_column(sa.Column('story_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_tasks_story_id', 'stories', ['story_id'], ['id'], ondelete='SET NULL')
            batch_op.create_index('idx_tasks_story_id', ['story_id'])
        if 'due_time' not in tasks_cols:
            batch_op.add_column(sa.Column('due_time', sa.Time(), nullable=True))


def downgrade():
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_index('idx_tasks_story_id')
        batch_op.drop_constraint('fk_tasks_story_id', type_='foreignkey')
        batch_op.drop_column('story_id')
        batch_op.drop_column('due_time')

    op.drop_table('stories')
    op.drop_table('epics')
