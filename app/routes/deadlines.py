from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_babel import gettext as _
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.models import Epic, Story
from app.utils.db import safe_commit
from app.utils.timezone import now_in_app_timezone
from app.routes.admin import admin_required

deadlines_bp = Blueprint("deadlines", __name__)


def _parse_deadline_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


@deadlines_bp.route("/deadlines/epics")
@login_required
@admin_required
def list_epics():
    """List Deadline: all Epics, not-yet-followed-up and soonest-due surfaced first"""
    epics = Epic.query.order_by(
        Epic.next_follow_up_date.asc().nulls_first(),
        Epic.deadline_date.asc().nulls_last(),
    ).all()
    return render_template("deadlines/list_epics.html", epics=epics, today=now_in_app_timezone().date())


@deadlines_bp.route("/deadlines/epics/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_epic():
    """Create a new top-level Epic"""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        deadline_date = _parse_deadline_date(request.form.get("deadline_date", ""))

        if not name:
            flash(_("Epic name is required"), "error")
            return render_template("deadlines/create_epic.html")

        epic = Epic(name=name, description=description or None, created_by=current_user.id, deadline_date=deadline_date)
        db.session.add(epic)
        if not safe_commit("create_epic", {}):
            flash(_("Could not create epic due to a database error"), "error")
            return render_template("deadlines/create_epic.html")

        flash(_('Epic "%(name)s" created successfully', name=epic.name), "success")
        return redirect(url_for("deadlines.view_epic", epic_id=epic.id))

    return render_template("deadlines/create_epic.html")


@deadlines_bp.route("/deadlines/epics/<int:epic_id>")
@login_required
@admin_required
def view_epic(epic_id):
    """View an Epic and its Stories"""
    epic = Epic.query.get_or_404(epic_id)
    stories = Story.query.filter_by(epic_id=epic.id).order_by(Story.status.asc(), Story.name.asc()).all()
    return render_template("deadlines/view_epic.html", epic=epic, stories=stories)


@deadlines_bp.route("/deadlines/epics/<int:epic_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_epic(epic_id):
    """Edit an existing Epic"""
    epic = Epic.query.get_or_404(epic_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "active").strip()
        deadline_date = _parse_deadline_date(request.form.get("deadline_date", ""))

        if not name:
            flash(_("Epic name is required"), "error")
            return render_template("deadlines/edit_epic.html", epic=epic)

        epic.name = name
        epic.description = description or None
        epic.status = status if status in ("active", "archived") else "active"
        epic.deadline_date = deadline_date

        if not safe_commit("edit_epic", {"epic_id": epic.id}):
            flash(_("Could not update epic due to a database error"), "error")
            return render_template("deadlines/edit_epic.html", epic=epic)

        flash(_('Epic "%(name)s" updated successfully', name=epic.name), "success")
        return redirect(url_for("deadlines.view_epic", epic_id=epic.id))

    return render_template("deadlines/edit_epic.html", epic=epic)


@deadlines_bp.route("/deadlines/stories/create", methods=["POST"])
@login_required
@admin_required
def create_story():
    """Create a new Story under an Epic"""
    epic_id = request.form.get("epic_id", type=int)
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    epic = Epic.query.get(epic_id) if epic_id else None
    if not epic:
        flash(_("Invalid epic"), "error")
        return redirect(url_for("deadlines.list_epics"))

    if not name:
        flash(_("Story name is required"), "error")
        return redirect(url_for("deadlines.view_epic", epic_id=epic.id))

    story = Story(epic_id=epic.id, name=name, description=description or None, created_by=current_user.id)
    db.session.add(story)
    if not safe_commit("create_story", {"epic_id": epic.id}):
        flash(_("Could not create story due to a database error"), "error")
        return redirect(url_for("deadlines.view_epic", epic_id=epic.id))

    flash(_('Story "%(name)s" added', name=story.name), "success")
    return redirect(url_for("deadlines.view_epic", epic_id=epic.id))


@deadlines_bp.route("/deadlines/stories/<int:story_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_story(story_id):
    """Edit an existing Story"""
    story = Story.query.get_or_404(story_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "open").strip()

        if not name:
            flash(_("Story name is required"), "error")
            return render_template("deadlines/edit_story.html", story=story)

        story.name = name
        story.description = description or None
        story.status = status if status in ("open", "done") else "open"

        if not safe_commit("edit_story", {"story_id": story.id}):
            flash(_("Could not update story due to a database error"), "error")
            return render_template("deadlines/edit_story.html", story=story)

        flash(_('Story "%(name)s" updated successfully', name=story.name), "success")
        return redirect(url_for("deadlines.view_epic", epic_id=story.epic_id))

    return render_template("deadlines/edit_story.html", story=story)
