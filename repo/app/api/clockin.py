"""Clock-in JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import clockin_service
from app.services.clockin_service import ClockInError

clockin_api_bp = Blueprint("clockin_api", __name__)


@clockin_api_bp.post("/clock-in")
@permission_required("clockin", "submit")
def clock_in():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()
    try:
        punch = clockin_service.validate_clock_in(
            user_id=actor.id if actor else int(data.get("user_id", 0)),
            face_match_score=float(data.get("face_match_score", 0)),
            brightness=float(data.get("brightness", 0)),
            face_count=int(data.get("face_count", 0)),
            device_id=data.get("device_id", ""),
            actor_id=actor.id if actor else None,
            punch_type="clock_in",
            face_image_hash=data.get("face_image_hash"),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"invalid input: {exc}"}), 400
    except ClockInError as exc:
        return jsonify({"error": str(exc)}), 400
    status = 200 if punch.success else 400
    return jsonify(punch.to_dict()), status


@clockin_api_bp.post("/clock-out")
@permission_required("clockin", "submit")
def clock_out():
    """Clock-out endpoint — skips biometric checks, only needs device_id."""
    data = request.get_json(silent=True) or {}
    actor = get_current_user()
    try:
        punch = clockin_service.validate_clock_in(
            user_id=actor.id if actor else int(data.get("user_id", 0)),
            device_id=data.get("device_id", ""),
            actor_id=actor.id if actor else None,
            punch_type="clock_out",
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"invalid input: {exc}"}), 400
    except ClockInError as exc:
        return jsonify({"error": str(exc)}), 400
    status = 200 if punch.success else 400
    return jsonify(punch.to_dict()), status
