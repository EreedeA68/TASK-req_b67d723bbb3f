"""Photographer scheduling model."""
from datetime import datetime

from app.db import db


class PhotographerSchedule(db.Model):
    __tablename__ = "photographer_schedules"

    id = db.Column(db.Integer, primary_key=True)
    photographer_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    type = db.Column(
        db.String(32), nullable=False, default="working"
    )  # working | break | off
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    photographer = db.relationship("User", backref="schedules", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "photographer_id": self.photographer_id,
            "date": self.date.isoformat() if self.date else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "type": self.type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
