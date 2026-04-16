"""Punch correction JSON API."""
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, login_required, permission_required
from app.services import correction_service
from app.services.correction_service import CorrectionError

corrections_api_bp = Blueprint("corrections_api", __name__)


@corrections_api_bp.post("")
@permission_required("correction", "submit")
def submit_correction():
    """Submit a missed-punch correction request."""
    data = request.get_json(silent=True) or {}
    actor = get_current_user()

    try:
        requested_time = datetime.fromisoformat(data.get("requested_time", ""))
    except (ValueError, TypeError):
        return jsonify({"error": "requested_time must be a valid ISO datetime"}), 400

    try:
        correction = correction_service.submit_correction(
            user_id=actor.id,
            punch_type=data.get("punch_type", ""),
            requested_time=requested_time,
            reason=data.get("reason", ""),
            original_punch_id=data.get("original_punch_id"),
            actor_id=actor.id,
        )
    except CorrectionError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(correction.to_dict()), 201


@corrections_api_bp.get("")
@login_required
def list_corrections():
    """List corrections. Admin sees all, others see own."""
    actor = get_current_user()
    pending_only = request.args.get("pending_only", "").lower() in ("1", "true", "yes")
    corrections = correction_service.list_corrections(
        actor_id=actor.id,
        pending_only=pending_only,
    )
    return jsonify([c.to_dict() for c in corrections])


@corrections_api_bp.post("/<int:correction_id>/approve")
@permission_required("correction", "review")
def approve_correction(correction_id):
    """Admin approves a correction — creates a corrected TimePunch."""
    actor = get_current_user()
    try:
        correction = correction_service.approve_correction(
            correction_id=correction_id,
            reviewer_id=actor.id,
        )
    except CorrectionError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(correction.to_dict())


@corrections_api_bp.post("/<int:correction_id>/reject")
@permission_required("correction", "review")
def reject_correction(correction_id):
    """Admin rejects a correction."""
    actor = get_current_user()
    try:
        correction = correction_service.reject_correction(
            correction_id=correction_id,
            reviewer_id=actor.id,
        )
    except CorrectionError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(correction.to_dict())
