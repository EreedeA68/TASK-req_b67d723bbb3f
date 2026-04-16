"""Receipt model — checkout receipt tied to an order."""
from datetime import datetime

from app.db import db


class Receipt(db.Model):
    __tablename__ = "receipts"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), nullable=False, unique=True
    )
    member_id = db.Column(
        db.Integer, db.ForeignKey("members.id"), nullable=False
    )
    subtotal = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, nullable=False, default=0.0)
    points_redeemed = db.Column(db.Integer, nullable=False, default=0)
    points_value = db.Column(db.Float, nullable=False, default=0.0)  # dollar value of redeemed points
    total = db.Column(db.Float, nullable=False)
    points_earned = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order = db.relationship(
        "Order", backref=db.backref("receipt", uselist=False), uselist=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "member_id": self.member_id,
            "subtotal": self.subtotal,
            "discount": self.discount,
            "points_redeemed": self.points_redeemed,
            "points_value": self.points_value,
            "total": self.total,
            "points_earned": self.points_earned,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
