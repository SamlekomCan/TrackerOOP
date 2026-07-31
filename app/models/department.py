from app import db
from app.utils.timezone import now_in_app_timezone


class Department(db.Model):
    """Department model - top-level organizational unit that scopes user visibility (privacy boundary)."""

    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    code = db.Column(db.String(20), nullable=True, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=now_in_app_timezone, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_in_app_timezone, onupdate=now_in_app_timezone, nullable=False)

    # Relationships
    members = db.relationship("User", backref="department", foreign_keys="User.department_id", lazy="dynamic")
    creator = db.relationship("User", foreign_keys=[created_by])

    def __init__(self, name, code=None, description=None, is_active=True, created_by=None):
        self.name = name.strip()
        self.code = code.strip().upper() if code else None
        self.description = description.strip() if description else None
        self.is_active = is_active
        self.created_by = created_by

    def __repr__(self):
        return f"<Department {self.id}: {self.name}>"
