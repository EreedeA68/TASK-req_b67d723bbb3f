"""Audit logging service — append-only writes."""
from app.db import db
from app.models.audit import AuditLog


def log(
    *,
    actor_id: int | None,
    action: str,
    resource: str,
    metadata: dict | None = None,
) -> AuditLog:
    """Append an audit record."""
    entry = AuditLog(actor_id=actor_id, action=action, resource=resource)
    entry.set_metadata(metadata or {})
    db.session.add(entry)
    db.session.commit()
    return entry


def list_all() -> list:
    return AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
