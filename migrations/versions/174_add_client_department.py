"""Add department_id to clients (Projects/Invoices inherit department scope through their Client)

Revision ID: 174_add_client_department
Revises: 173_add_departments
Create Date: 2026-07-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '174_add_client_department'
down_revision = '173_add_departments'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    clients_cols = {c['name'] for c in inspector.get_columns('clients')}

    if 'department_id' not in clients_cols:
        with op.batch_alter_table('clients') as batch_op:
            batch_op.add_column(sa.Column('department_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_clients_department_id', 'departments', ['department_id'], ['id']
            )
        op.create_index('idx_clients_department_id', 'clients', ['department_id'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    clients_cols = {c['name'] for c in inspector.get_columns('clients')} if 'clients' in inspector.get_table_names() else set()

    if 'department_id' in clients_cols:
        op.drop_index('idx_clients_department_id', table_name='clients')
        with op.batch_alter_table('clients') as batch_op:
            batch_op.drop_constraint('fk_clients_department_id', type_='foreignkey')
            batch_op.drop_column('department_id')
