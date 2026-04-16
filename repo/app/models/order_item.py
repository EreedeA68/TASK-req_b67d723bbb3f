"""OrderItem model — line items for an order."""
from datetime import datetime

from app.db import db


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(64), nullable=False)  # drink, dessert, grill, salad, etc.
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False, default=0.0)
    allergy_note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order = db.relationship("Order", backref="items", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "name": self.name,
            "category": self.category,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "allergy_note": self.allergy_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
