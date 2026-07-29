"""Add deadline and follow-up tracking fields to epics (List Deadline view)

Revision ID: 110_add_epic_deadline_followup
Revises: 109_remove_epic_project
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '110_add_epic_deadline_followup'
down_revision = '109_remove_epic_project'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    epics_cols = {c['name'] for c in inspector.get_columns('epics')}

    with op.batch_alter_table('epics') as batch_op:
        if 'deadline_date' not in epics_cols:
            batch_op.add_column(sa.Column('deadline_date', sa.Date(), nullable=True))
            batch_op.create_index('idx_epics_deadline_date', ['deadline_date'])
        if 'follow_up_notes' not in epics_cols:
            batch_op.add_column(sa.Column('follow_up_notes', sa.Text(), nullable=True))
        if 'next_follow_up_date' not in epics_cols:
            batch_op.add_column(sa.Column('next_follow_up_date', sa.Date(), nullable=True))
            batch_op.create_index('idx_epics_next_follow_up_date', ['next_follow_up_date'])
        if 'last_follow_up_at' not in epics_cols:
            batch_op.add_column(sa.Column('last_follow_up_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('epics') as batch_op:
        batch_op.drop_index('idx_epics_next_follow_up_date')
        batch_op.drop_index('idx_epics_deadline_date')
        batch_op.drop_column('last_follow_up_at')
        batch_op.drop_column('next_follow_up_date')
        batch_op.drop_column('follow_up_notes')
        batch_op.drop_column('deadline_date')
