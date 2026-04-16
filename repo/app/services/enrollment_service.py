"""Biometric enrollment service — admin-managed reference capture."""
import hashlib

from app.db import db
from app.models.enrollment import Enrollment
from app.models.user import User
from app.services import audit_service


class EnrollmentError(Exception):
    """Error in enrollment operations."""


def _compute_reference_hash(reference_data: str) -> str:
    """Compute SHA-256 of the reference artifact (image bytes, template, etc.)."""
    if not reference_data:
        raise EnrollmentError("reference_data is required")
    return hashlib.sha256(reference_data.encode()).hexdigest()


def create_or_update(
    user_id: int,
    reference_data: str,
    device_id: str | None = None,
    *,
    actor_id: int | None = None,
) -> Enrollment:
    """Create or replace the active enrollment for a user.

    Any existing active enrollment is deactivated first so that each user
    has at most one active reference at a time.
    """
    user = db.session.get(User, user_id)
    if user is None:
        raise EnrollmentError("user not found")

    reference_hash = _compute_reference_hash(reference_data)

    # Deactivate any existing active enrollment
    existing = Enrollment.query.filter_by(user_id=user_id, active=True).all()
    for e in existing:
        e.active = False

    enrollment = Enrollment(
        user_id=user_id,
        reference_hash=reference_hash,
        device_id=device_id,
        active=True,
    )
    db.session.add(enrollment)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="enrollment_created",
        resource=f"user:{user_id}",
        metadata={
            "enrollment_id": enrollment.id,
            "device_id": device_id,
            "replaced_count": len(existing),
        },
    )
    return enrollment


def deactivate(user_id: int, *, actor_id: int | None = None) -> int:
    """Deactivate all active enrollments for a user."""
    active = Enrollment.query.filter_by(user_id=user_id, active=True).all()
    for e in active:
        e.active = False
    db.session.commit()
    count = len(active)
    if count > 0:
        audit_service.log(
            actor_id=actor_id,
            action="enrollment_deactivated",
            resource=f"user:{user_id}",
            metadata={"count": count},
        )
    return count


def get_for_user(user_id: int) -> Enrollment | None:
    """Return the current active enrollment for a user, if any."""
    return Enrollment.query.filter_by(user_id=user_id, active=True).first()


def list_enrollments() -> list[Enrollment]:
    """Return all enrollments (admin-only)."""
    return Enrollment.query.order_by(Enrollment.id).all()
