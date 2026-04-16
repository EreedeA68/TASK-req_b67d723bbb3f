"""Booking model with locking mechanism."""
from datetime import datetime

from app.db import db


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer, db.ForeignKey("members.id"), nullable=False, index=True
    )
    photographer_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(
        db.String(32), nullable=False, default="locked"
    )  # locked | confirmed | cancelled
    lock_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    member = db.relationship("Member", backref="bookings", lazy="joined")
    photographer = db.relationship(
        "User", foreign_keys=[photographer_id], backref="bookings", lazy="joined"
    )
    creator = db.relationship(
        "User", foreign_keys=[created_by], lazy="joined"
    )

    def is_lock_expired(self) -> bool:
        if self.status != "locked":
            return False
        if self.lock_expires_at is None:
            return False
        return datetime.utcnow() >= self.lock_expires_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "member_id": self.member_id,
            "photographer_id": self.photographer_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "lock_expires_at": (
                self.lock_expires_at.isoformat() if self.lock_expires_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
