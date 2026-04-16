"""CSV export service."""
import csv
import os
from datetime import datetime

from flask import current_app

from app.core.encryption import mask_phone, mask_balance
from app.db import db
from app.models.booking import Booking
from app.models.export import ExportJob
from app.models.member import Member
from app.models.order import Order
from app.services import audit_service
from app.services.member_service import _decrypt_phone, _decrypt_balance


class ExportError(Exception):
    """Error in export operations."""


VALID_TYPES = {"orders", "members", "bookings"}


def create_export(
    export_type: str,
    *,
    actor_id: int | None = None,
    is_admin: bool = False,
) -> ExportJob:
    if export_type not in VALID_TYPES:
        raise ExportError(f"invalid export type; must be one of {sorted(VALID_TYPES)}")

    export_dir = current_app.config.get("EXPORT_DIR", "exports")
    os.makedirs(export_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{export_type}_{timestamp}.csv"
    filepath = os.path.join(export_dir, filename)

    if export_type == "orders":
        _export_orders(filepath, actor_id=actor_id, is_admin=is_admin)
    elif export_type == "members":
        _export_members(filepath, actor_id=actor_id, is_admin=is_admin)
    elif export_type == "bookings":
        _export_bookings(filepath, actor_id=actor_id, is_admin=is_admin)

    job = ExportJob(
        user_id=actor_id or 0,
        type=export_type,
        file_path=filepath,
    )
    db.session.add(job)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="export_completed",
        resource=f"export:{job.id}",
        metadata={"type": export_type, "file_path": filepath},
    )
    return job


def _export_orders(filepath: str, *, actor_id: int | None = None, is_admin: bool = False) -> None:
    query = Order.query
    if not is_admin and actor_id is not None:
        query = query.filter(Order.created_by == actor_id)
    rows = query.order_by(Order.created_at).all()
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "member_id", "status", "subtotal", "discount", "total", "created_at"])
        for r in rows:
            w.writerow([r.id, r.member_id, r.status, r.subtotal, r.discount, r.total,
                        r.created_at.isoformat() if r.created_at else ""])


def _export_members(filepath: str, *, actor_id: int | None = None, is_admin: bool = False) -> None:
    from sqlalchemy import or_
    query = Member.query
    if not is_admin and actor_id is not None:
        actor_member_ids = (
            db.session.query(Order.member_id).filter(Order.created_by == actor_id)
            .union(
                db.session.query(Booking.member_id).filter(
                    or_(Booking.created_by == actor_id, Booking.photographer_id == actor_id)
                )
            )
        )
        query = query.filter(Member.id.in_(actor_member_ids))
    rows = query.order_by(Member.created_at).all()
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "member_id", "phone_number", "tier",
                     "points_balance", "stored_value_balance", "created_at"])
        for r in rows:
            phone = _decrypt_phone(r)
            balance = _decrypt_balance(r)
            # Mask PII for non-admin exports
            if not is_admin:
                phone = mask_phone(phone)
                balance = mask_balance(balance)
            w.writerow([r.id, r.name, r.member_id, phone, r.tier,
                        r.points_balance, balance,
                        r.created_at.isoformat() if r.created_at else ""])


def _export_bookings(filepath: str, *, actor_id: int | None = None, is_admin: bool = False) -> None:
    from sqlalchemy import or_
    query = Booking.query
    if not is_admin and actor_id is not None:
        query = query.filter(
            or_(Booking.created_by == actor_id, Booking.photographer_id == actor_id)
        )
    rows = query.order_by(Booking.created_at).all()
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "member_id", "photographer_id", "start_time", "end_time",
                     "status", "created_at"])
        for r in rows:
            w.writerow([r.id, r.member_id, r.photographer_id,
                        r.start_time.isoformat() if r.start_time else "",
                        r.end_time.isoformat() if r.end_time else "",
                        r.status,
                        r.created_at.isoformat() if r.created_at else ""])


def list_exports(
    *,
    actor_id: int | None = None,
    is_admin: bool = False,
) -> list[ExportJob]:
    """Return export jobs scoped by actor.

    Admin sees all; other roles only see their own export jobs.  This
    enforces least-privilege on export metadata (file paths, timestamps).
    """
    query = ExportJob.query
    if not is_admin and actor_id is not None:
        query = query.filter(ExportJob.user_id == actor_id)
    return query.order_by(ExportJob.created_at.desc()).all()
