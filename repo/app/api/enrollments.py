"""Biometric enrollment JSON API (admin-only)."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import enrollment_service
from app.services.enrollment_service import EnrollmentError

enrollments_api_bp = Blueprint("enrollments_api", __name__)


@enrollments_api_bp.get("")
@permission_required("enrollment", "view")
def list_enrollments():
    entries = enrollment_service.list_enrollments()
    return jsonify({"results": [e.to_dict() for e in entries]})


@enrollments_api_bp.get("/<int:user_id>")
@permission_required("enrollment", "view")
def get_enrollment(user_id: int):
    enrollment = enrollment_service.get_for_user(user_id)
    if enrollment is None:
        return jsonify({"error": "no active enrollment"}), 404
    return jsonify(enrollment.to_dict())


@enrollments_api_bp.post("/<int:user_id>")
@permission_required("enrollment", "manage")
def create_or_update(user_id: int):
    """Create or replace the active enrollment for the given user."""
    data = request.get_json(silent=True) or {}
    reference_data = data.get("reference_data")
    device_id = data.get("device_id")
    if not reference_data or not isinstance(reference_data, str):
        return jsonify({"error": "reference_data is required"}), 400

    actor = get_current_user()
    try:
        enrollment = enrollment_service.create_or_update(
            user_id=user_id,
            reference_data=reference_data,
            device_id=device_id,
            actor_id=actor.id if actor else None,
        )
    except EnrollmentError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg else 400
        return jsonify({"error": msg}), status

    return jsonify(enrollment.to_dict()), 201


@enrollments_api_bp.delete("/<int:user_id>")
@permission_required("enrollment", "manage")
def deactivate(user_id: int):
    """Deactivate all active enrollments for the user."""
    actor = get_current_user()
    count = enrollment_service.deactivate(
        user_id, actor_id=actor.id if actor else None,
    )
    return jsonify({"deactivated": count})
