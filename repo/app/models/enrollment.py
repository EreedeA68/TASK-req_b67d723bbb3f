"""Clock-in enrollment model — stores reference biometric data per user."""
from datetime import datetime

from app.db import db


class Enrollment(db.Model):
    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    reference_hash = db.Column(db.String(255), nullable=False)
    device_id = db.Column(db.String(255), nullable=True)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    user = db.relationship("User", backref="enrollment", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "enrolled_at": self.enrolled_at.isoformat() if self.enrolled_at else None,
            "active": self.active,
        }
