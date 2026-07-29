from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_babel import gettext as _
from flask_login import login_required, current_user
from app import db
from app.models import TrendingIssue, User
from app.utils.db import safe_commit
from app.utils.permissions import admin_or_permission_required

trending_issues_bp = Blueprint("trending_issues", __name__)


@trending_issues_bp.route("/trending-issues")
@login_required
def list_trending_issues():
    """List all trending issues, open ones surfaced first."""
    issues = TrendingIssue.query.order_by(
        TrendingIssue.status.asc(), TrendingIssue.created_at.desc()
    ).all()
    return render_template("trending_issues/list_trending_issues.html", issues=issues)


@trending_issues_bp.route("/trending-issues/create", methods=["GET", "POST"])
@login_required
@admin_or_permission_required("manage_trending_issues")
def create_trending_issue():
    """Create a new trending issue (management only)."""
    users = User.query.order_by(User.username).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        detail = request.form.get("detail", "").strip()
        pic_id = request.form.get("pic_id", type=int)

        if not name:
            flash(_("Issue name is required"), "error")
            return render_template("trending_issues/create_trending_issue.html", users=users)

        issue = TrendingIssue(name=name, detail=detail or None, pic_id=pic_id or None, created_by=current_user.id)
        db.session.add(issue)
        if not safe_commit("create_trending_issue", {}):
            flash(_("Could not create trending issue due to a database error"), "error")
            return render_template("trending_issues/create_trending_issue.html", users=users)

        flash(_('Trending issue "%(name)s" created successfully', name=issue.name), "success")
        return redirect(url_for("trending_issues.list_trending_issues"))

    return render_template("trending_issues/create_trending_issue.html", users=users)


@trending_issues_bp.route("/trending-issues/<int:issue_id>")
@login_required
def view_trending_issue(issue_id):
    """View a trending issue."""
    issue = TrendingIssue.query.get_or_404(issue_id)
    return render_template("trending_issues/view_trending_issue.html", issue=issue)


@trending_issues_bp.route("/trending-issues/<int:issue_id>/edit", methods=["GET", "POST"])
@login_required
@admin_or_permission_required("manage_trending_issues")
def edit_trending_issue(issue_id):
    """Edit an existing trending issue (management only)."""
    issue = TrendingIssue.query.get_or_404(issue_id)
    users = User.query.order_by(User.username).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        detail = request.form.get("detail", "").strip()
        pic_id = request.form.get("pic_id", type=int)
        status = request.form.get("status", "open").strip()

        if not name:
            flash(_("Issue name is required"), "error")
            return render_template("trending_issues/edit_trending_issue.html", issue=issue, users=users)

        issue.name = name
        issue.detail = detail or None
        issue.pic_id = pic_id or None
        issue.status = status if status in ("open", "resolved") else "open"

        if not safe_commit("edit_trending_issue", {"issue_id": issue.id}):
            flash(_("Could not update trending issue due to a database error"), "error")
            return render_template("trending_issues/edit_trending_issue.html", issue=issue, users=users)

        flash(_('Trending issue "%(name)s" updated successfully', name=issue.name), "success")
        return redirect(url_for("trending_issues.view_trending_issue", issue_id=issue.id))

    return render_template("trending_issues/edit_trending_issue.html", issue=issue, users=users)


@trending_issues_bp.route("/trending-issues/<int:issue_id>/delete", methods=["POST"])
@login_required
@admin_or_permission_required("manage_trending_issues")
def delete_trending_issue(issue_id):
    """Delete a trending issue (management only)."""
    issue = TrendingIssue.query.get_or_404(issue_id)
    issue_name = issue.name

    db.session.delete(issue)
    if not safe_commit("delete_trending_issue", {"issue_id": issue_id}):
        flash(_("Could not delete trending issue due to a database error"), "error")
        return redirect(url_for("trending_issues.list_trending_issues"))

    flash(_('Trending issue "%(name)s" deleted', name=issue_name), "success")
    return redirect(url_for("trending_issues.list_trending_issues"))
