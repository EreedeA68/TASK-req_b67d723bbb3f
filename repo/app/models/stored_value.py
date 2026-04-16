"""Stored-value ledger model."""
from datetime import datetime

from app.db import db


class StoredValueLedger(db.Model):
    __tablename__ = "stored_value_ledger"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer, db.ForeignKey("members.id"), nullable=False, index=True
    )
    type = db.Column(db.String(16), nullable=False)  # credit / debit
    amount = db.Column(db.Float, nullable=False)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), nullable=True
    )
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    member = db.relationship("Member", backref="stored_value_entries", lazy="joined")
    order = db.relationship("Order", backref="stored_value_entries", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "member_id": self.member_id,
            "type": self.type,
            "amount": self.amount,
            "order_id": self.order_id,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
