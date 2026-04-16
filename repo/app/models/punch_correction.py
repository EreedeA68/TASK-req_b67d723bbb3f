"""Punch correction request model."""
from datetime import datetime

from app.db import db


class PunchCorrection(db.Model):
    __tablename__ = "punch_corrections"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    original_punch_id = db.Column(db.Integer, db.ForeignKey("time_punches.id"), nullable=True)
    requested_type = db.Column(db.String(16), nullable=False)  # clock_in | clock_out
    requested_time = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending")  # pending | approved | rejected
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", foreign_keys=[user_id], backref="punch_corrections")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    original_punch = db.relationship("TimePunch", backref="corrections")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "original_punch_id": self.original_punch_id,
            "requested_type": self.requested_type,
            "requested_time": self.requested_time.isoformat() if self.requested_time else None,
            "reason": self.reason,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
