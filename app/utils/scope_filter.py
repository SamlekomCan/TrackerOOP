"""Scope filtering: restrict data to assigned clients/projects (subcontractors, client portal users)."""

from typing import Set, Tuple

from flask_login import current_user


def get_allowed_client_ids(user=None):
    """Return allowed client IDs for user, or None for full access. Uses current_user if user is None."""
    u = user or (current_user if current_user.is_authenticated else None)
    if not u:
        return []
    return u.get_allowed_client_ids()


def get_allowed_project_ids(user=None):
    """Return allowed project IDs for user, or None for full access. Uses current_user if user is None."""
    u = user or (current_user if current_user.is_authenticated else None)
    if not u:
        return []
    return u.get_allowed_project_ids()


def apply_client_scope(Client, query, user=None):
    """Apply client scope to a Client query. Returns query with scope filter applied if restricted."""
    scope = apply_client_scope_to_model(Client, user)
    if scope is None:
        return query
    return query.filter(scope)


def apply_project_scope(Project, query, user=None):
    """Apply project scope to a Project query. Returns query with scope filter applied if restricted."""
    scope = apply_project_scope_to_model(Project, user)
    if scope is None:
        return query
    return query.filter(scope)


def apply_client_scope_to_model(Client, user=None):
    """Return filter expression for Client query (Client.id.in_(...) or None for no filter)."""
    u = user or (current_user if current_user.is_authenticated else None)
    if not u or u.is_admin:
        return None
    allowed = u.get_allowed_client_ids()
    if allowed is None:
        return None
    if not allowed:
        return Client.id.in_([])  # never match
    return Client.id.in_(allowed)


def apply_project_scope_to_model(Project, user=None):
    """Return filter expression for Project query (Project.id.in_(...) or None for no filter)."""
    u = user or (current_user if current_user.is_authenticated else None)
    if not u or u.is_admin:
        return None
    allowed_projects = u.get_allowed_project_ids()
    if allowed_projects is None:
        return None
    if not allowed_projects:
        return Project.id.in_([])  # never match
    return Project.id.in_(allowed_projects)


def user_can_access_client(user, client_id):
    """Return True if user may access this client (for direct ID checks / 403)."""
    if not user:
        return False
    if user.is_admin:
        return True
    allowed = user.get_allowed_client_ids()
    if allowed is None:
        return True
    return client_id in allowed


def user_can_access_project(user, project_id):
    """Return True if user may access this project (for direct ID checks / 403)."""
    if not user:
        return False
    if user.is_admin:
        return True
    allowed = user.get_allowed_project_ids()
    if allowed is None:
        return True
    return project_id in allowed


def get_allowed_department_ids(user=None):
    """Return allowed department IDs for user, or None for full access. Uses current_user if user is None."""
    u = user or (current_user if current_user.is_authenticated else None)
    if not u:
        return []
    return u.get_allowed_department_ids()


def user_can_access_department(user, department_id):
    """Return True if user may access this department (for direct ID checks / 403)."""
    if not user:
        return False
    if user.is_admin:
        return True
    allowed = user.get_allowed_department_ids()
    if allowed is None:
        return True
    return department_id in allowed


def get_department_scoped_user_ids(user=None):
    """Return user IDs within the current user's department scope, or None for full access.

    Used to filter records that don't carry their own department_id but are
    tied to a user (created_by, assigned_to, pic_id, ...) whose department
    determines visibility.
    """
    from app import db
    from app.models import User

    u = user or (current_user if current_user.is_authenticated else None)
    if not u:
        return []
    allowed_dept_ids = u.get_allowed_department_ids()
    if allowed_dept_ids is None:
        return None
    if not allowed_dept_ids:
        return []
    rows = db.session.query(User.id).filter(User.department_id.in_(allowed_dept_ids)).all()
    return [r[0] for r in rows]


def combine_id_scopes(*id_scopes):
    """Combine multiple allowed-id-list-or-None scopes with AND semantics.

    Each argument is either None (unrestricted for that dimension) or a list of
    allowed IDs. Returns None only if every scope is unrestricted; otherwise
    returns the intersection of all restrictive scopes (so a user must pass
    every applicable scope, e.g. subcontractor client assignment AND
    department, to see a record).
    """
    restrictive = [s for s in id_scopes if s is not None]
    if not restrictive:
        return None
    result = set(restrictive[0])
    for s in restrictive[1:]:
        result &= set(s)
    return list(result)


def get_department_scoped_client_ids(user=None):
    """Return client IDs within the current user's department scope, or None for full access."""
    from app.models import Client

    allowed_dept_ids = get_allowed_department_ids(user)
    if allowed_dept_ids is None:
        return None
    if not allowed_dept_ids:
        return []
    rows = Client.query.with_entities(Client.id).filter(Client.department_id.in_(allowed_dept_ids)).all()
    return [r[0] for r in rows]


def get_department_scoped_project_ids(user=None):
    """Return project IDs (via their Client's department) within the current user's
    department scope, or None for full access."""
    from app.models import Client, Project

    allowed_dept_ids = get_allowed_department_ids(user)
    if allowed_dept_ids is None:
        return None
    if not allowed_dept_ids:
        return []
    rows = (
        Project.query.with_entities(Project.id)
        .join(Client, Project.client_id == Client.id)
        .filter(Client.department_id.in_(allowed_dept_ids))
        .all()
    )
    return [r[0] for r in rows]


def get_report_scoped_user_ids(user=None):
    """Return user IDs whose time-entry-backed reports the current user may view, or None
    for full access. Bounds the "view_all_time_entries" permission (e.g. manager role) to
    the user's own department instead of the whole company; admins stay unrestricted."""
    u = user or (current_user if current_user.is_authenticated else None)
    if not u:
        return []
    if u.is_admin:
        return None
    if u.has_permission("view_all_time_entries"):
        return get_department_scoped_user_ids(u)
    return [u.id]


def apply_department_scope_to_model(model_department_column, query, user=None):
    """Filter `query` to rows whose own `model_department_column` (a FK to departments.id,
    e.g. Client.department_id) is within the current user's department scope.
    No-op for admins (full access). A row with department_id=None is excluded for
    scoped (non-admin) users -- it hasn't been assigned to a department yet.
    """
    allowed_dept_ids = get_allowed_department_ids(user)
    if allowed_dept_ids is None:
        return query
    if not allowed_dept_ids:
        return query.filter(model_department_column.in_([]))  # never match
    return query.filter(model_department_column.in_(allowed_dept_ids))


def user_can_access_department_owned_record(department_id, user=None):
    """Return True if a record whose own department_id is `department_id` is within
    the current user's department scope (for direct-URL 403 checks)."""
    allowed_dept_ids = get_allowed_department_ids(user)
    if allowed_dept_ids is None:
        return True
    if department_id is None:
        return False
    return department_id in allowed_dept_ids


def user_can_access_via_department_scope(owner_user_id, user=None):
    """Return True if `owner_user_id` (the user who owns/created a record) is within the
    current user's department scope -- for direct-URL 403 checks on records filtered out
    of list views by apply_department_scope_via_user_field."""
    allowed_user_ids = get_department_scoped_user_ids(user)
    if allowed_user_ids is None:
        return True
    if owner_user_id is None:
        return False
    return owner_user_id in allowed_user_ids


def apply_department_scope_via_user_field(model_user_column, query, user=None):
    """Filter `query` to rows whose `model_user_column` (a FK to users.id) belongs to a user
    in the current user's department. No-op for admins (full access).

    Example: apply_department_scope_via_user_field(Epic.created_by, Epic.query)
    """
    allowed_user_ids = get_department_scoped_user_ids(user)
    if allowed_user_ids is None:
        return query
    if not allowed_user_ids:
        return query.filter(model_user_column.in_([]))  # never match
    return query.filter(model_user_column.in_(allowed_user_ids))


def get_active_clients_for_user(user, *, status="active"):
    """Return clients visible to user (respects scope)."""
    from app.models import Client

    query = Client.query.filter_by(status=status).order_by(Client.name)
    scope = apply_client_scope_to_model(Client, user)
    if scope is not None:
        query = query.filter(scope)
    return query.all()


def get_active_projects_for_user(user, *, status="active"):
    """Return projects visible to user (respects scope)."""
    from app.models import Project

    query = Project.query.filter_by(status=status).order_by(Project.name)
    scope = apply_project_scope_to_model(Project, user)
    if scope is not None:
        query = query.filter(scope)
    return query.all()


def get_accessible_project_and_client_ids_for_user(user_id: int) -> Tuple[Set[int], Set[int]]:
    """
    Return (accessible_project_ids, accessible_client_ids) for issue-style access:
    projects the user has time entries for or is assigned to tasks on, and clients of those projects.
    Used to filter issues for non-admin users without view_all_issues permission.
    """
    from app.models import Project, Task
    from app.repositories import TimeEntryRepository

    time_entry_repo = TimeEntryRepository()
    user_project_ids = set(time_entry_repo.get_distinct_project_ids_for_user(user_id))
    task_project_rows = (
        Task.query.with_entities(Task.project_id)
        .filter_by(assigned_to=user_id)
        .filter(Task.project_id.isnot(None))
        .distinct()
        .all()
    )
    task_project_ids = {r[0] for r in task_project_rows}
    all_accessible_project_ids = user_project_ids | task_project_ids
    if not all_accessible_project_ids:
        return set(), set()
    client_rows = (
        Project.query.with_entities(Project.client_id)
        .filter(Project.id.in_(all_accessible_project_ids), Project.client_id.isnot(None))
        .distinct()
        .all()
    )
    accessible_client_ids = {r[0] for r in client_rows}
    return all_accessible_project_ids, accessible_client_ids
