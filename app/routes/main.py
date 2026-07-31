import os
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import text

from app import csrf, db, limiter, track_page_view
from app.models import (
    Activity,
    Client,
    Epic,
    Project,
    Story,
    Task,
    TimeEntry,
    TimeEntryTemplate,
    TrendingIssue,
    User,
    WeeklyTimeGoal,
)
from app.models.time_entry import local_now
from app.utils.posthog_segmentation import update_user_segments_if_needed
from app.utils.timezone import now_in_app_timezone

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@main_bp.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard showing active timer and recent entries - REFACTORED to use services and fix N+1 queries"""
    # Track dashboard page view
    track_page_view("dashboard")

    # Update user segments periodically (cached, not every request)
    update_user_segments_if_needed(current_user.id, current_user)

    # Do not cache dashboard template_data: it contains ORM objects (active_timer,
    # recent_entries, top_projects, templates, etc.) that become detached when
    # served in a different request, causing "Instance not bound to a Session"
    # and "Database Error" on second visit (Issue #549).

    # Get user's active timer
    active_timer = current_user.active_timer

    # Get recent entries for the user (using repository to avoid N+1)
    from app.repositories import TimeEntryRepository

    time_entry_repo = TimeEntryRepository()
    recent_entries = time_entry_repo.get_by_user(user_id=current_user.id, limit=10, include_relations=True)

    # Get the user's checked-in tasks for the Upcoming Task widget.
    # Managers see their whole department's Member tasks; everyone else sees only their own.
    from sqlalchemy.orm import joinedload

    from app.utils.scope_filter import apply_department_scope_via_user_field

    upcoming_tasks_base = Task.query.filter(Task.source == "check_in", Task.status.in_(["todo", "in_progress"]))
    if current_user.is_manager and not current_user.is_admin:
        upcoming_tasks_query = apply_department_scope_via_user_field(Task.assigned_to, upcoming_tasks_base)
    else:
        upcoming_tasks_query = upcoming_tasks_base.filter(Task.assigned_to == current_user.id)
    upcoming_checkin_tasks = (
        upcoming_tasks_query.options(joinedload(Task.story).joinedload(Story.epic), joinedload(Task.assigned_user))
        .order_by(Task.due_date.asc().nulls_last())
        .limit(10)
        .all()
    )
    # Subset the current user can actually check out / delete (their own tasks, or all if admin).
    # Managers see the wider department list above for visibility, but Check-Out/Update/Delete
    # still only act on tasks they're assigned to, created, or (as admin) own outright.
    own_checkin_tasks = [
        t
        for t in upcoming_checkin_tasks
        if current_user.is_admin or t.assigned_to == current_user.id or t.created_by == current_user.id
    ]

    # Get active epics for the Check-In Epic -> Story dropdown (scoped to own department)
    epics = (
        apply_department_scope_via_user_field(Epic.created_by, Epic.query.filter_by(status="active"))
        .order_by(Epic.next_follow_up_date.asc().nulls_first(), Epic.deadline_date.asc().nulls_last())
        .all()
    )

    # Get trending issues for the dashboard box (open ones first, most recent; scoped to own department)
    trending_issues = (
        apply_department_scope_via_user_field(TrendingIssue.created_by, TrendingIssue.query)
        .order_by(TrendingIssue.status.asc(), TrendingIssue.created_at.desc())
        .limit(5)
        .all()
    )

    # Get active projects and clients for timer dropdown (scoped for subcontractors)
    from app.utils.scope_filter import apply_client_scope_to_model, apply_project_scope_to_model

    projects_query = Project.query.filter_by(status="active").order_by(Project.name)
    scope_p = apply_project_scope_to_model(Project, current_user)
    if scope_p is not None:
        projects_query = projects_query.filter(scope_p)
    active_projects = projects_query.all()
    clients_query = Client.query.filter_by(status="active").order_by(Client.name)
    scope_c = apply_client_scope_to_model(Client, current_user)
    if scope_c is not None:
        clients_query = clients_query.filter(scope_c)
    active_clients = clients_query.all()
    only_one_client = len(active_clients) == 1
    single_client = active_clients[0] if only_one_client else None

    # Get user statistics and dashboard aggregations (cached 90s to reduce DB load)
    from app.services import AnalyticsService
    from app.utils.cache import get_cache
    from app.utils.overtime import calculate_period_overtime, get_overtime_ytd, get_week_start_for_date

    dashboard_stats_key = f"dashboard:stats:{current_user.id}"
    dashboard_chart_key = f"dashboard:chart:{current_user.id}"
    cache = get_cache()
    stats = cache.get(dashboard_stats_key)
    chart_data = cache.get(dashboard_chart_key)

    if stats is None or chart_data is None:
        analytics_service = AnalyticsService()
        if stats is None:
            stats = analytics_service.get_dashboard_stats(user_id=current_user.id)
            try:
                cache.set(dashboard_stats_key, stats, ttl=90)
            except Exception:
                # Cache is best-effort; a miss just means recomputing next request.
                current_app.logger.debug("Could not cache dashboard stats", exc_info=True)
        if chart_data is None:
            chart_data = analytics_service.get_time_by_project_chart(current_user.id, days=7, limit=10)
            try:
                cache.set(dashboard_chart_key, chart_data, ttl=90)
            except Exception:
                current_app.logger.debug("Could not cache dashboard chart data", exc_info=True)

    today_hours = stats["time_tracking"]["today_hours"]
    week_hours = stats["time_tracking"]["week_hours"]
    month_hours = stats["time_tracking"]["month_hours"]
    workday_today_hours = stats.get("workday_hours", {}).get("today", 0.0)
    workday_week_hours = stats.get("workday_hours", {}).get("week", 0.0)
    workday_month_hours = stats.get("workday_hours", {}).get("month", 0.0)

    from app.services.attendance_compliance_service import AttendanceComplianceService
    from app.services.workday_session_service import WorkdaySessionService
    from app.services.working_time_limit_service import WorkingTimeLimitService

    workday_svc = WorkdaySessionService()
    active_workday_session = workday_svc.get_active_session(current_user.id)
    attendance_status = AttendanceComplianceService().get_status(current_user.id)
    attendance_break_active = attendance_status.get("break_active", False)
    overnight_open_workday = workday_svc.is_overnight_open_session(active_workday_session)
    suggested_leave_time = (
        workday_svc.suggested_leave_datetime_local(active_workday_session, current_user)
        if overnight_open_workday and active_workday_session
        else None
    )
    pending_violations = WorkingTimeLimitService().get_violations_needing_justification(current_user.id)

    # Overtime for dashboard cards (today and week)
    today_dt = datetime.utcnow().date()
    week_start_dt = get_week_start_for_date(today_dt, current_user)
    today_overtime = calculate_period_overtime(current_user, today_dt, today_dt)
    week_overtime = calculate_period_overtime(current_user, week_start_dt, today_dt)
    overtime_ytd = get_overtime_ytd(current_user)
    standard_hours_per_day = float(getattr(current_user, "standard_hours_per_day", 8.0) or 8.0)

    # Top projects (last 30 days) - not cached (contains ORM refs for template links)
    analytics_service = AnalyticsService()
    top_projects = analytics_service.get_dashboard_top_projects(current_user.id, days=30, limit=5)
    time_by_project_7d = chart_data["series"]
    chart_labels_7d = chart_data["chart_labels"]
    chart_hours_7d = chart_data["chart_hours"]

    # Get current week goal
    current_week_goal = WeeklyTimeGoal.get_current_week_goal(current_user.id)
    if current_week_goal:
        current_week_goal.update_status()

    # Get user's time entry templates (most recently used first)
    from sqlalchemy import desc
    from sqlalchemy.orm import joinedload

    templates = (
        TimeEntryTemplate.query.options(joinedload(TimeEntryTemplate.project), joinedload(TimeEntryTemplate.task))
        .filter_by(user_id=current_user.id)
        .order_by(desc(TimeEntryTemplate.last_used_at))
        .limit(5)
        .all()
    )

    # Get recent activities for activity feed widget
    recent_activities = Activity.get_recent(user_id=None if current_user.is_admin else current_user.id, limit=10)

    # Recent tags for Start Timer modal autocomplete (distinct from user's time entries)
    recent_tags = []
    tag_rows = (
        db.session.query(TimeEntry.tags)
        .filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.tags.isnot(None),
            TimeEntry.tags != "",
        )
        .order_by(TimeEntry.updated_at.desc())
        .limit(200)
        .all()
    )
    tags_seen = set()
    for (tags_str,) in tag_rows:
        if tags_str:
            for part in tags_str.split(","):
                t = part.strip()
                if t and t not in tags_seen:
                    tags_seen.add(t)
                    recent_tags.append(t)
                    if len(recent_tags) >= 30:
                        break
        if len(recent_tags) >= 30:
            break

    # Last timer context: most recent completed time entry for "Repeat last" / quick start
    last_entry = (
        TimeEntry.query.options(
            joinedload(TimeEntry.project),
            joinedload(TimeEntry.client),
        )
        .filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.isnot(None),
        )
        .order_by(TimeEntry.end_time.desc())
        .limit(1)
        .first()
    )
    last_timer_context = None
    if last_entry and (last_entry.project_id or last_entry.client_id):
        last_timer_context = {
            "project_id": last_entry.project_id,
            "task_id": last_entry.task_id,
            "client_id": last_entry.client_id,
            "notes": (last_entry.notes or "").strip(),
            "tags": (last_entry.tags or "").strip(),
            "project_name": last_entry.project.name if last_entry.project else None,
            "client_name": last_entry.client.name if last_entry.client else None,
        }

    # Post-timer toast data (show "Logged Xh on Project" + link to time entries)
    timer_stopped_toast = session.pop("timer_stopped_toast", None)
    if timer_stopped_toast:
        timer_stopped_toast["time_entries_url"] = url_for("timer.time_entries_overview")

    # Prepare template data
    template_data = {
        "active_timer": active_timer,
        "active_workday_session": active_workday_session,
        "attendance_break_active": attendance_break_active,
        "overnight_open_workday": overnight_open_workday,
        "suggested_leave_time": suggested_leave_time,
        "workday_today_hours": workday_today_hours,
        "workday_week_hours": workday_week_hours,
        "workday_month_hours": workday_month_hours,
        "pending_violations": pending_violations,
        "recent_entries": recent_entries,
        "active_projects": active_projects,
        "active_clients": active_clients,
        "only_one_client": only_one_client,
        "single_client": single_client,
        "today_hours": today_hours,
        "week_hours": week_hours,
        "month_hours": month_hours,
        "standard_hours_per_day": standard_hours_per_day,
        "today_regular_hours": today_overtime["regular_hours"],
        "today_overtime_hours": today_overtime["overtime_hours"],
        "week_regular_hours": week_overtime["regular_hours"],
        "week_overtime_hours": week_overtime["overtime_hours"],
        "overtime_ytd_hours": overtime_ytd["overtime_hours"],
        "overtime_ytd_regular": overtime_ytd["regular_hours"],
        "top_projects": top_projects,
        "time_by_project_7d": time_by_project_7d,
        "chart_labels_7d": chart_labels_7d,
        "chart_hours_7d": chart_hours_7d,
        "current_week_goal": current_week_goal,
        "templates": templates,
        "recent_activities": recent_activities,
        "last_timer_context": last_timer_context,
        "recent_tags": recent_tags,
        "timer_stopped_toast": timer_stopped_toast,
        "upcoming_checkin_tasks": upcoming_checkin_tasks,
        "own_checkin_tasks": own_checkin_tasks,
        "today_iso": now_in_app_timezone().date().isoformat(),
        "today": now_in_app_timezone().date(),
        "epics": epics,
        "trending_issues": trending_issues,
    }

    return render_template("main/dashboard.html", **template_data)


@main_bp.route("/dashboard/productivity")
@login_required
def productivity_dashboard():
    """Personal productivity dashboard: streaks, focus, project mix, heatmap."""
    track_page_view("productivity_dashboard")

    from app.services.productivity_service import ProductivityService

    summary = ProductivityService.get_summary(current_user)
    daily_breakdown = ProductivityService.get_daily_breakdown(current_user, days=14)
    streak = ProductivityService.get_streak(current_user)
    focus = ProductivityService.get_focus_stats(current_user, days=30)
    projects = ProductivityService.get_project_breakdown(current_user, days=30)
    heatmap = ProductivityService.get_weekly_heatmap(current_user, weeks=12)
    insights = ProductivityService.get_insights(current_user, summary, daily_breakdown, streak, focus, projects)

    standard_hours_per_day = float(getattr(current_user, "standard_hours_per_day", 8.0) or 8.0)

    return render_template(
        "main/productivity_dashboard.html",
        summary=summary,
        daily_breakdown=daily_breakdown,
        streak=streak,
        focus=focus,
        projects=projects,
        heatmap=heatmap,
        insights=insights,
        standard_hours_per_day=standard_hours_per_day,
        period_days=30,
    )


@main_bp.route("/_health")
def health_check():
    """Liveness probe: shallow checks only, no DB access"""
    return {"status": "healthy"}, 200


@main_bp.route("/_ready")
def readiness_check():
    """Readiness probe: verify DB connectivity and critical dependencies"""
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ready", "timestamp": local_now().isoformat()}, 200
    except Exception as e:
        return {"status": "not_ready", "error": "db_unreachable"}, 503


@main_bp.route("/about")
def about():
    """About page"""
    return render_template("main/about.html")


@main_bp.route("/help")
def help():
    """Help page"""
    return render_template("main/help.html")


@main_bp.route("/debug/i18n")
@login_required
def debug_i18n():
    """Debug endpoint to check i18n status (admin only)"""
    from flask_login import current_user

    if not current_user.is_admin:
        return jsonify({"error": "Admin only"}), 403

    import os

    from flask_babel import get_locale

    locale = str(get_locale())
    session_lang = session.get("preferred_language")
    user_lang = getattr(current_user, "preferred_language", None)

    # Check if .mo file exists for current locale
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    translations_dir = os.path.join(base_path, "translations")
    mo_path = os.path.join(translations_dir, locale, "LC_MESSAGES", "messages.mo")
    po_path = os.path.join(translations_dir, locale, "LC_MESSAGES", "messages.po")

    return jsonify(
        {
            "current_locale": locale,
            "session_language": session_lang,
            "user_language": user_lang,
            "mo_file_exists": os.path.exists(mo_path),
            "po_file_exists": os.path.exists(po_path),
            "mo_path": mo_path,
            "nb_mo_exists": os.path.exists(os.path.join(translations_dir, "nb", "LC_MESSAGES", "messages.mo")),
            "no_mo_exists": os.path.exists(os.path.join(translations_dir, "no", "LC_MESSAGES", "messages.mo")),
        }
    )


@main_bp.route("/i18n/set-language", methods=["POST", "GET"])
def set_language():
    """Set preferred UI language via session or user profile."""
    lang = (
        request.args.get("lang")
        or (request.form.get("lang") if request.method == "POST" else None)
        or (request.json.get("lang") if request.is_json else None)
        or "en"
    )
    lang = lang.strip().lower()
    from flask import current_app

    supported = list(current_app.config.get("LANGUAGES", {}).keys()) or ["en"]
    if lang not in supported:
        lang = current_app.config.get("BABEL_DEFAULT_LOCALE", "en")

    # Make session permanent to ensure it persists across requests
    session.permanent = True

    # Persist in session for guests
    session["preferred_language"] = lang
    session.modified = True  # Force session save

    # If authenticated, persist to user profile
    try:
        from flask_login import current_user

        if current_user and getattr(current_user, "is_authenticated", False):
            # Update user preference in database
            current_user.preferred_language = lang
            # Add to session and commit
            db.session.add(current_user)
            db.session.commit()
            # Expire all cached objects to ensure fresh load on next request
            db.session.expire_all()
    except Exception as e:
        # If database save fails, rollback but continue with session
        try:
            db.session.rollback()
        except Exception:
            # A rollback that itself fails leaves the session unusable — surface it.
            current_app.logger.error("Rollback failed after settings save error", exc_info=True)

    # Redirect back if referer exists, add timestamp to force reload
    next_url = request.headers.get("Referer") or url_for("main.dashboard")
    # Add cache-busting parameter to ensure fresh page load
    import time

    separator = "&" if "?" in next_url else "?"
    next_url = f"{next_url}{separator}_lang_refresh={int(time.time())}"
    response = make_response(redirect(next_url))
    # Ensure no caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@main_bp.route("/search")
@login_required
def search():
    """Search time entries"""
    query = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    if not query:
        return redirect(url_for("main.dashboard"))

    # Search in time entries
    from sqlalchemy import or_

    entries = (
        TimeEntry.query.filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.isnot(None),
            or_(TimeEntry.notes.ilike(f"%{query}%"), TimeEntry.tags.ilike(f"%{query}%")),
        )
        .order_by(TimeEntry.start_time.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )

    return render_template("main/search.html", entries=entries, query=query)


@main_bp.route("/manifest.webmanifest")
def manifest():
    """Legacy URL: canonical manifest is /static/manifest.json."""
    return redirect(url_for("static", filename="manifest.json"), code=302)


@main_bp.route("/offline")
def offline_page():
    """Public offline fallback for PWA (no login required)."""
    resp = make_response(render_template("offline.html"))
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@main_bp.route("/service-worker.js")
def service_worker():
    """Site-scoped service worker; implementation lives in app/static/js/sw.js."""
    return send_from_directory(current_app.static_folder, "js/sw.js", mimetype="application/javascript")


@main_bp.route("/csp-report", methods=["POST"])
@csrf.exempt
@limiter.limit("60 per hour")
def csp_report():
    """
    Collection point for Content-Security-Policy violation reports.

    The strict, nonce-based policy ships as Content-Security-Policy-Report-Only (see
    apply_security_headers in app/__init__.py) so violations can be observed before the
    policy is enforced. Without a report-uri the browser has nowhere to send them —
    Firefox warns that such a policy "will not block and cannot report violations" — so
    the reports only reached each user's own console, where nobody sees them.

    Unauthenticated and CSRF-exempt by necessity: the browser posts these itself, with
    no session or token. Rate-limited because the endpoint is world-writable and a
    misconfigured or hostile client could otherwise flood the log.
    """
    payload = request.get_json(force=True, silent=True) or {}
    report = payload.get("csp-report", payload)

    if not isinstance(report, dict):
        return "", 204

    current_app.logger.warning(
        "CSP violation: directive=%s blocked=%s document=%s",
        report.get("violated-directive") or report.get("effective-directive") or "?",
        report.get("blocked-uri") or "?",
        report.get("document-uri") or "?",
    )
    return "", 204
