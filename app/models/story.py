from app import db
from app.utils.timezone import now_in_app_timezone


class Story(db.Model):
    """Story model - a unit of work under an Epic (Jira-like). Tasks created via Check-In link to a Story."""

    __tablename__ = "stories"

    id = db.Column(db.Integer, primary_key=True)
    epic_id = db.Column(db.Integer, db.ForeignKey("epics.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="open", nullable=False, index=True)  # 'open', 'done'
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=now_in_app_timezone, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_in_app_timezone, onupdate=now_in_app_timezone, nullable=False)

    # Relationships
    # epic relationship is defined via backref in Epic model
    # tasks relationship is defined via backref in Task model
    creator = db.relationship("User", foreign_keys=[created_by])

    def __init__(self, epic_id, name, description=None, status="open", created_by=None):
        self.epic_id = epic_id
        self.name = name.strip()
        self.description = description.strip() if description else None
        self.status = status
        self.created_by = created_by

    def __repr__(self):
        return f"<Story {self.id}: {self.name}>"
