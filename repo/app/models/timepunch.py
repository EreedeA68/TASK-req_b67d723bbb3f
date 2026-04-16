"""Clock-in / TimePunch model."""
from datetime import datetime

from app.db import db


class TimePunch(db.Model):
    __tablename__ = "time_punches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    punch_type = db.Column(db.String(16), nullable=False, default="clock_in")  # clock_in | clock_out
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    device_fingerprint = db.Column(db.String(255), nullable=True)
    success = db.Column(db.Boolean, nullable=False, default=False)
    reason = db.Column(db.String(255), nullable=True)
    signature = db.Column(db.String(255), nullable=True)
    canonical_hash = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="time_punches", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "punch_type": self.punch_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "device_fingerprint": self.device_fingerprint,
            "success": self.success,
            "reason": self.reason,
            "signature": self.signature,
            "canonical_hash": self.canonical_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
