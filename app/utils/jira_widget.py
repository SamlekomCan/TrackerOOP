"""Shared data-fetch for the Dashboard's Jira Sprint Backlog widget.

Used by both the main dashboard render and the AJAX board-switch endpoint so
the two stay in sync (see app/routes/integrations.py:jira_dashboard_widget).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import current_app


def get_jira_widget_data(board_name: Optional[str] = None) -> Dict[str, Any]:
    """Fetch the active sprint's first 5 issues for the Dashboard widget.

    Best-effort: the Jira host is often only reachable from inside the
    corporate network/VPN, so this must never raise -- callers get back a
    dict with success=False instead.
    """
    try:
        from app.services.integration_service import IntegrationService

        integration_service = IntegrationService()
        jira_integration = integration_service.get_global_integration("jira")
        if not (jira_integration and jira_integration.is_active):
            return {"success": False, "message": "Jira integration is not configured."}

        connector = integration_service.get_connector(jira_integration)
        if not connector:
            return {"success": False, "message": "Could not initialize Jira connector."}

        result = connector.get_active_sprint_backlog(board_name=board_name)
        all_issues = result.get("issues") or []
        result["total_count"] = len(all_issues)
        result["issues"] = all_issues[:5]
        return result
    except Exception as e:
        current_app.logger.warning("Jira dashboard widget failed: %s", e)
        return {"success": False, "message": str(e)}


def get_jira_boards_for_widget() -> List[Dict[str, Any]]:
    """List the boards (squads) for the Dashboard widget's board dropdown, scoped to
    the configured 'jira_project_key' so the list stays short. Best-effort: returns
    an empty list on any failure rather than breaking the dashboard.
    """
    try:
        from app.services.integration_service import IntegrationService

        integration_service = IntegrationService()
        jira_integration = integration_service.get_global_integration("jira")
        if not (jira_integration and jira_integration.is_active):
            return []

        connector = integration_service.get_connector(jira_integration)
        if not connector:
            return []

        result = connector.list_boards_for_project()
        return result.get("boards", []) if result.get("success") else []
    except Exception as e:
        current_app.logger.warning("Jira boards list failed: %s", e)
        return []
