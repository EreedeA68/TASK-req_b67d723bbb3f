"""KDS (Kitchen Display System) ticket model."""
from datetime import datetime

from app.db import db


class KDSTicket(db.Model):
    __tablename__ = "kds_tickets"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True
    )
    station = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(
        db.String(32), nullable=False, default="pending"
    )  # pending | in_progress | done
    priority = db.Column(db.Integer, nullable=False, default=0)
    eta_minutes = db.Column(db.Integer, nullable=False, default=15)
    allergy_flag = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order = db.relationship("Order", backref="kds_tickets", lazy="joined")

    def minutes_late(self) -> int:
        """Return how many minutes past the ETA this ticket is (0 if on-time or done)."""
        from datetime import timedelta

        if self.status == "done":
            return 0
        deadline = self.created_at + timedelta(minutes=self.eta_minutes)
        now = datetime.utcnow()
        if now <= deadline:
            return 0
        return int((now - deadline).total_seconds() // 60)

    def is_late(self) -> bool:
        return self.minutes_late() > 0

    def late_alert(self) -> str | None:
        """Return a human-readable lateness alert (or None if on-time/done)."""
        minutes = self.minutes_late()
        if minutes <= 0:
            return None
        return f"late by {minutes} min"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "station": self.station,
            "status": self.status,
            "priority": self.priority,
            "eta_minutes": self.eta_minutes,
            "allergy_flag": self.allergy_flag,
            "is_late": self.is_late(),
            "minutes_late": self.minutes_late(),
            "late_alert": self.late_alert(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
