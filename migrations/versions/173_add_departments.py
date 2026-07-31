"""Add departments table and users.department_id for per-department data privacy

Revision ID: 173_add_departments
Revises: 172_merge_recovered_features_head
Create Date: 2026-07-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime
from sqlalchemy import Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import table, column

# revision identifiers, used by Alembic.
revision = '173_add_departments'
down_revision = '172_merge_recovered_features_head'
branch_labels = None
depends_on = None

departments_table = table(
    'departments',
    column('id', Integer),
    column('name', String),
    column('code', String),
    column('description', Text),
    column('is_active', Boolean),
    column('created_by', Integer),
    column('created_at', DateTime),
    column('updated_at', DateTime),
)

SEED_DEPARTMENTS = [
    {'name': 'OOP', 'code': 'OOP'},
    {'name': 'CNS', 'code': 'CNS'},
    {'name': 'IMP', 'code': 'IMP'},
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'departments' not in existing_tables:
        op.create_table(
            'departments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('code', sa.String(length=20), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='uq_departments_name'),
            sa.UniqueConstraint('code', name='uq_departments_code'),
        )
        op.create_index('idx_departments_name', 'departments', ['name'])
        op.create_index('idx_departments_code', 'departments', ['code'])
        op.create_index('idx_departments_is_active', 'departments', ['is_active'])

        now = datetime.utcnow()
        op.bulk_insert(
            departments_table,
            [
                {
                    'name': d['name'],
                    'code': d['code'],
                    'description': None,
                    'is_active': True,
                    'created_by': None,
                    'created_at': now,
                    'updated_at': now,
                }
                for d in SEED_DEPARTMENTS
            ],
        )

    users_cols = {c['name'] for c in inspector.get_columns('users')}
    if 'department_id' not in users_cols:
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(sa.Column('department_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_users_department_id', 'departments', ['department_id'], ['id']
            )
        op.create_index('idx_users_department_id', 'users', ['department_id'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    users_cols = {c['name'] for c in inspector.get_columns('users')} if 'users' in existing_tables else set()
    if 'department_id' in users_cols:
        op.drop_index('idx_users_department_id', table_name='users')
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_constraint('fk_users_department_id', type_='foreignkey')
            batch_op.drop_column('department_id')

    if 'departments' in existing_tables:
        op.drop_index('idx_departments_is_active', table_name='departments')
        op.drop_index('idx_departments_code', table_name='departments')
        op.drop_index('idx_departments_name', table_name='departments')
        op.drop_table('departments')
