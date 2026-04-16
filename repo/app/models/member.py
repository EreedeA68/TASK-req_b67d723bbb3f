"""Member domain model."""
from datetime import datetime

from app.db import db


class Member(db.Model):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(32), index=True, nullable=False)
    # Deterministic SHA-256 HMAC of the normalized phone number for fast lookup
    # without decrypting every row.  Indexed for O(log n) search.
    phone_hash = db.Column(db.String(64), index=True, nullable=True)
    member_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    tier = db.Column(db.String(32), default="standard", nullable=False)
    points_balance = db.Column(db.Integer, default=0, nullable=False)
    # Phase 1 placeholder — will be encrypted in a later phase.
    stored_value_balance = db.Column(db.String(255), default="0", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    orders = db.relationship("Order", backref="member", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone_number": self.phone_number,
            "member_id": self.member_id,
            "tier": self.tier,
            "points_balance": self.points_balance,
            "stored_value_balance": self.stored_value_balance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
