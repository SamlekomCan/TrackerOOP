"""Add source column to tasks for check-in/check-out workflow

Revision ID: 107_add_task_source
Revises: 106_add_po_role
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '107_add_task_source'
down_revision = '106_add_po_role'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tasks_cols = {c['name'] for c in inspector.get_columns('tasks')}

    if 'source' not in tasks_cols:
        with op.batch_alter_table('tasks') as batch_op:
            batch_op.add_column(
                sa.Column('source', sa.String(length=20), nullable=True, server_default='manual')
            )


def downgrade():
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_column('source')
