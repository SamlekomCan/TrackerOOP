"""Remove project_id from epics - Epic is a top-level entity, not tied to a Project

Revision ID: 109_remove_epic_project
Revises: 108_add_epic_story
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '109_remove_epic_project'
down_revision = '108_add_epic_story'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    epics_cols = {c['name'] for c in inspector.get_columns('epics')}

    if 'project_id' in epics_cols:
        with op.batch_alter_table('epics') as batch_op:
            batch_op.drop_index('idx_epics_project_id')
            batch_op.drop_constraint('epics_project_id_fkey', type_='foreignkey')
            batch_op.drop_column('project_id')


def downgrade():
    with op.batch_alter_table('epics') as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('epics_project_id_fkey', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index('idx_epics_project_id', ['project_id'])
