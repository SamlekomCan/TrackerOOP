from app import db
from app.utils.timezone import now_in_app_timezone


class Epic(db.Model):
    """Epic model - a top-level body of work grouping related Stories (Jira-like). Not tied to a Project."""

    __tablename__ = "epics"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False, index=True)  # 'active', 'archived'
    deadline_date = db.Column(db.Date, nullable=True, index=True)
    # Follow-up fields are auto-filled from Check-Out on tasks linked to this epic's stories, not user-edited
    follow_up_notes = db.Column(db.Text, nullable=True)
    next_follow_up_date = db.Column(db.Date, nullable=True, index=True)
    last_follow_up_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=now_in_app_timezone, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_in_app_timezone, onupdate=now_in_app_timezone, nullable=False)

    # Relationships
    stories = db.relationship("Story", backref="epic", cascade="all, delete-orphan", lazy="dynamic")
    creator = db.relationship("User", foreign_keys=[created_by])

    def __init__(
        self,
        name,
        description=None,
        status="active",
        created_by=None,
        deadline_date=None,
        follow_up_notes=None,
        next_follow_up_date=None,
        last_follow_up_at=None,
    ):
        self.name = name.strip()
        self.description = description.strip() if description else None
        self.status = status
        self.created_by = created_by
        self.deadline_date = deadline_date
        self.follow_up_notes = follow_up_notes
        self.next_follow_up_date = next_follow_up_date
        self.last_follow_up_at = last_follow_up_at

    def __repr__(self):
        return f"<Epic {self.id}: {self.name}>"
