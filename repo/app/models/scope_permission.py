"""Configurable scope-based permission model for hybrid RBAC/ABAC."""
from datetime import datetime

from app.db import db


class ScopePermission(db.Model):
    __tablename__ = "scope_permissions"

    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(64), nullable=False, index=True)
    resource = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(64), nullable=False)
    scope_type = db.Column(db.String(32), nullable=True)   # location, station, employee, field, record, menu, api
    scope_value = db.Column(db.String(128), nullable=True)  # e.g., "station:grill", "location:main", "menu:orders", "api:/api/orders"
    granted = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role_name": self.role_name,
            "resource": self.resource,
            "action": self.action,
            "scope_type": self.scope_type,
            "scope_value": self.scope_value,
            "granted": self.granted,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
