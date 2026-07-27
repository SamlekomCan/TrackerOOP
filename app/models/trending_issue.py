from app import db
from app.utils.timezone import now_in_app_timezone


class TrendingIssue(db.Model):
    """A trending issue tracked by management: issue name, PIC, and detail."""

    __tablename__ = "trending_issues"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    detail = db.Column(db.Text, nullable=True)
    pic_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(20), default="open", nullable=False, index=True)  # 'open', 'resolved'
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=now_in_app_timezone, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_in_app_timezone, onupdate=now_in_app_timezone, nullable=False)

    pic = db.relationship("User", foreign_keys=[pic_id])
    creator = db.relationship("User", foreign_keys=[created_by])

    def __init__(self, name, detail=None, pic_id=None, status="open", created_by=None):
        self.name = name.strip()
        self.detail = detail.strip() if detail else None
        self.pic_id = pic_id
        self.status = status
        self.created_by = created_by

    def __repr__(self):
        return f"<TrendingIssue {self.id}: {self.name}>"
