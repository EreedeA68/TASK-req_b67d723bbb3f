"""Points ledger model for the points economy."""
from datetime import datetime, timedelta

from app.db import db

POINTS_EXPIRY_DAYS = 365


class PointLedger(db.Model):
    __tablename__ = "point_ledger"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer, db.ForeignKey("members.id"), nullable=False, index=True
    )
    type = db.Column(db.String(16), nullable=False)  # earn | redeem
    points = db.Column(db.Integer, nullable=False)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)

    member = db.relationship("Member", backref="point_ledger_entries", lazy="joined")
    order = db.relationship("Order", backref="point_ledger_entries", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "member_id": self.member_id,
            "type": self.type,
            "points": self.points,
            "order_id": self.order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
