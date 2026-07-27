"""Add PO (Product Owner) role

Revision ID: 106_add_po_role
Revises: 105_fix_client_notifications_cascade_delete
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.sql import table, column

# revision identifiers, used by Alembic.
revision = '106_add_po_role'
down_revision = '105_fix_client_notifications_cascade_delete'
branch_labels = None
depends_on = None

ROLE_NAME = 'po'
ROLE_DESCRIPTION = 'Product Owner'

# Baseline permission set (same as the "user" role) - can be refined later
PERMISSION_NAMES = [
    'view_own_time_entries',
    'create_time_entries',
    'edit_own_time_entries',
    'delete_own_time_entries',
    'view_projects',
    'view_own_tasks',
    'create_tasks',
    'edit_own_tasks',
    'delete_own_tasks',
    'view_clients',
    'view_own_invoices',
    'view_own_reports',
    'export_reports',
    'view_inventory',
    'view_stock_levels',
]

roles_table = table(
    'roles',
    column('id', Integer),
    column('name', String),
    column('description', String),
    column('is_system_role', Boolean),
    column('created_at', DateTime),
    column('updated_at', DateTime),
)

role_permissions_table = table(
    'role_permissions',
    column('role_id', Integer),
    column('permission_id', Integer),
    column('created_at', DateTime),
)


def upgrade():
    connection = op.get_bind()
    now = datetime.utcnow()

    existing_role = connection.execute(
        sa.text("SELECT id FROM roles WHERE name = :name"), {"name": ROLE_NAME}
    ).fetchone()

    if existing_role:
        role_id = existing_role[0]
    else:
        connection.execute(
            roles_table.insert().values(
                name=ROLE_NAME,
                description=ROLE_DESCRIPTION,
                is_system_role=True,
                created_at=now,
                updated_at=now,
            )
        )
        role_id = connection.execute(
            sa.text("SELECT id FROM roles WHERE name = :name"), {"name": ROLE_NAME}
        ).fetchone()[0]

    if PERMISSION_NAMES:
        placeholders = ", ".join(f":p{i}" for i in range(len(PERMISSION_NAMES)))
        params = {f"p{i}": name for i, name in enumerate(PERMISSION_NAMES)}
        perm_rows = connection.execute(
            sa.text(f"SELECT id FROM permissions WHERE name IN ({placeholders})"), params
        ).fetchall()

        existing_role_perm_ids = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT permission_id FROM role_permissions WHERE role_id = :rid"),
                {"rid": role_id},
            ).fetchall()
        }

        rows_to_insert = [
            {"role_id": role_id, "permission_id": perm_row[0], "created_at": now}
            for perm_row in perm_rows
            if perm_row[0] not in existing_role_perm_ids
        ]

        if rows_to_insert:
            connection.execute(role_permissions_table.insert(), rows_to_insert)


def downgrade():
    connection = op.get_bind()

    existing_role = connection.execute(
        sa.text("SELECT id FROM roles WHERE name = :name"), {"name": ROLE_NAME}
    ).fetchone()

    if existing_role:
        role_id = existing_role[0]
        connection.execute(sa.text("DELETE FROM user_roles WHERE role_id = :rid"), {"rid": role_id})
        connection.execute(sa.text("DELETE FROM role_permissions WHERE role_id = :rid"), {"rid": role_id})
        connection.execute(sa.text("DELETE FROM roles WHERE id = :rid"), {"rid": role_id})
