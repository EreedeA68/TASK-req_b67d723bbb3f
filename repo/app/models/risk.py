"""Fraud / risk flag model."""
from datetime import datetime

from app.db import db


class RiskFlag(db.Model):
    __tablename__ = "risk_flags"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=True, index=True)
    type = db.Column(db.String(64), nullable=False)  # points_abuse | spend_abuse
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="risk_flags", lazy="joined")
    member = db.relationship("Member", backref="risk_flags", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "member_id": self.member_id,
            "type": self.type,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
