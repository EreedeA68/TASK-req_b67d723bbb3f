"""Punch correction workflow service."""
from datetime import datetime

from app.db import db
from app.models.punch_correction import PunchCorrection
from app.models.timepunch import TimePunch
from app.models.user import User
from app.services import audit_service


class CorrectionError(Exception):
    """Error in correction operations."""


def submit_correction(
    *,
    user_id: int,
    punch_type: str,
    requested_time: datetime,
    reason: str,
    original_punch_id: int | None = None,
    actor_id: int | None = None,
) -> PunchCorrection:
    """Submit a missed-punch correction request for admin review."""
    if punch_type not in ("clock_in", "clock_out"):
        raise CorrectionError("punch_type must be clock_in or clock_out")
    if not reason or not reason.strip():
        raise CorrectionError("reason is required")
    if db.session.get(User, user_id) is None:
        raise CorrectionError("user not found")

    correction = PunchCorrection(
        user_id=user_id,
        original_punch_id=original_punch_id,
        requested_type=punch_type,
        requested_time=requested_time,
        reason=reason.strip(),
        status="pending",
    )
    db.session.add(correction)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id or user_id,
        action="correction_submitted",
        resource=f"correction:{correction.id}",
        metadata={
            "user_id": user_id,
            "punch_type": punch_type,
            "requested_time": requested_time.isoformat(),
            "reason": reason.strip(),
        },
    )
    return correction


def list_corrections(
    *,
    actor_id: int | None = None,
    pending_only: bool = False,
) -> list[PunchCorrection]:
    """List correction requests.

    Admin users see all corrections. Non-admin users see only their own.
    """
    query = PunchCorrection.query

    if actor_id is not None:
        user = db.session.get(User, actor_id)
        if user and "admin" not in user.role_names():
            query = query.filter_by(user_id=actor_id)

    if pending_only:
        query = query.filter_by(status="pending")

    return query.order_by(PunchCorrection.created_at.desc()).all()


def approve_correction(
    *,
    correction_id: int,
    reviewer_id: int,
) -> PunchCorrection:
    """Approve a correction and create a corrected TimePunch."""
    correction = db.session.get(PunchCorrection, correction_id)
    if correction is None:
        raise CorrectionError("correction not found")
    if correction.status != "pending":
        raise CorrectionError(f"correction already {correction.status}")

    now = datetime.utcnow()

    # Update correction status
    correction.status = "approved"
    correction.reviewed_by = reviewer_id
    correction.reviewed_at = now

    # Compute tamper-evident signature using the clockin service's scheme.
    # Including reviewer_id + correction_id in the canonical payload keeps
    # the signature unique per correction approval and bound to the
    # server secret.
    from app.services import clockin_service
    device_id = f"correction:{correction.id}"
    canonical = clockin_service._canonical_hash(
        correction.user_id,
        correction.requested_type,
        device_id,
        f"correction:{reviewer_id}",
        0.0,
        1,
    )
    nonce = clockin_service._make_nonce()
    signature = clockin_service._make_signature(
        correction.user_id,
        correction.requested_type,
        device_id,
        nonce,
        f"correction:{reviewer_id}",
        0.0,
        1,
    )

    # Create the corrected TimePunch with the same integrity scheme as a
    # regular clock-in/out punch.
    punch = TimePunch(
        user_id=correction.user_id,
        punch_type=correction.requested_type,
        timestamp=correction.requested_time,
        device_fingerprint=device_id,
        success=True,
        reason=f"approved_correction:{correction.id}",
        signature=signature,
        canonical_hash=canonical,
    )
    db.session.add(punch)
    db.session.commit()

    audit_service.log(
        actor_id=reviewer_id,
        action="correction_approved",
        resource=f"correction:{correction.id}",
        metadata={
            "correction_id": correction.id,
            "user_id": correction.user_id,
            "punch_type": correction.requested_type,
            "punch_id": punch.id,
        },
    )
    return correction


def reject_correction(
    *,
    correction_id: int,
    reviewer_id: int,
) -> PunchCorrection:
    """Reject a correction request."""
    correction = db.session.get(PunchCorrection, correction_id)
    if correction is None:
        raise CorrectionError("correction not found")
    if correction.status != "pending":
        raise CorrectionError(f"correction already {correction.status}")

    now = datetime.utcnow()
    correction.status = "rejected"
    correction.reviewed_by = reviewer_id
    correction.reviewed_at = now
    db.session.commit()

    audit_service.log(
        actor_id=reviewer_id,
        action="correction_rejected",
        resource=f"correction:{correction.id}",
        metadata={
            "correction_id": correction.id,
            "user_id": correction.user_id,
        },
    )
    return correction
