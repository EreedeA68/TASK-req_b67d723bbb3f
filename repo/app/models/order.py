"""Order and OrderEvent models."""
from datetime import datetime

from app.db import db


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer, db.ForeignKey("members.id"), nullable=False, index=True
    )
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    status = db.Column(db.String(32), default="created", nullable=False, index=True)
    subtotal = db.Column(db.Float, default=0.0, nullable=False)
    discount = db.Column(db.Float, default=0.0, nullable=False)
    total = db.Column(db.Float, default=0.0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    events = db.relationship(
        "OrderEvent",
        backref="order",
        lazy="dynamic",
        order_by="OrderEvent.timestamp",
    )

    def to_dict(self) -> dict:
        deadline = self.deadline_at()
        return {
            "id": self.id,
            "member_id": self.member_id,
            "status": self.status,
            "subtotal": self.subtotal,
            "discount": self.discount,
            "total": self.total,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "deadline_at": deadline.isoformat() if deadline else None,
        }

    def _last_event_time(self, status: str):
        """Return timestamp of the most recent event with the given status."""
        event = (
            OrderEvent.query
            .filter_by(order_id=self.id, status=status)
            .order_by(OrderEvent.timestamp.desc())
            .first()
        )
        return event.timestamp if event else None

    def deadline_at(self):
        """Return the next expiry deadline (UTC) for the current status."""
        from datetime import timedelta

        from app.services.expiry_service import (
            PICKUP_EXPIRY_MINUTES, READY_EXPIRY_MINUTES, UNPAID_EXPIRY_MINUTES,
        )
        if self.status == "created":
            return self.created_at + timedelta(minutes=UNPAID_EXPIRY_MINUTES)
        if self.status == "ready":
            ready_at = self._last_event_time("ready") or self.created_at
            return ready_at + timedelta(minutes=READY_EXPIRY_MINUTES)
        if self.status == "ready_for_pickup":
            pickup_at = self._last_event_time("ready_for_pickup") or self.created_at
            return pickup_at + timedelta(minutes=PICKUP_EXPIRY_MINUTES)
        return None


class OrderEvent(db.Model):
    __tablename__ = "order_events"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    status = db.Column(db.String(32), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "status": self.status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor_id": self.actor_id,
        }
