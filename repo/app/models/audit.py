"""Audit log model — append-only, write-once immutable."""
import json
from datetime import datetime

from sqlalchemy import event

from app.db import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    resource = db.Column(db.String(120), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    meta = db.Column(db.Text, nullable=True)  # JSON string

    def set_metadata(self, data: dict) -> None:
        self.meta = json.dumps(data) if data else None

    def get_metadata(self) -> dict:
        if not self.meta:
            return {}
        try:
            return json.loads(self.meta)
        except (ValueError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "action": self.action,
            "resource": self.resource,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.get_metadata(),
        }


# Write-once immutability: prevent updates and deletes at the ORM level.
@event.listens_for(AuditLog, "before_update")
def _block_audit_update(mapper, connection, target):
    raise RuntimeError("AuditLog records are immutable and cannot be updated")


@event.listens_for(AuditLog, "before_delete")
def _block_audit_delete(mapper, connection, target):
    raise RuntimeError("AuditLog records are immutable and cannot be deleted")
