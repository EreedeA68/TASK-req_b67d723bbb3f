"""Clock-in / clock-out kiosk view."""
from datetime import datetime

from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.services import clockin_service, correction_service
from app.services.clockin_service import ClockInError
from app.services.correction_service import CorrectionError

clockin_view_bp = Blueprint("clockin_view", __name__)


@clockin_view_bp.get("/clock-in")
@permission_required("clockin", "submit")
def clockin_page():
    return render_template("clockin.html", user=get_current_user(), result=None)


@clockin_view_bp.post("/clock-in/submit")
@permission_required("clockin", "submit")
def do_clockin():
    actor = get_current_user()
    # Forward the captured artifact hash to the service so strict-mode
    # deployments accept kiosk submissions. If the field is blank the
    # service falls back to client-claim mode (non-strict only).
    face_image_hash = (request.form.get("face_image_hash") or "").strip() or None
    try:
        punch = clockin_service.validate_clock_in(
            user_id=actor.id,
            face_match_score=float(request.form.get("face_match_score", 0)),
            brightness=float(request.form.get("brightness", 0)),
            face_count=int(request.form.get("face_count", 0)),
            device_id=request.form.get("device_id", ""),
            actor_id=actor.id,
            punch_type="clock_in",
            face_image_hash=face_image_hash,
        )
    except (TypeError, ValueError, ClockInError) as exc:
        return render_template(
            "partials/clockin_result.html", result=None, error=str(exc)
        ), 400
    return render_template(
        "partials/clockin_result.html", result=punch, error=None
    )


@clockin_view_bp.post("/clock-in/clock-out")
@permission_required("clockin", "submit")
def do_clockout():
    """Clock-out from kiosk — skips biometric checks."""
    actor = get_current_user()
    try:
        punch = clockin_service.validate_clock_in(
            user_id=actor.id,
            device_id=request.form.get("device_id", ""),
            actor_id=actor.id,
            punch_type="clock_out",
        )
    except (TypeError, ValueError, ClockInError) as exc:
        return render_template(
            "partials/clockout_result.html", result=None, error=str(exc)
        ), 400
    return render_template(
        "partials/clockout_result.html", result=punch, error=None
    )


@clockin_view_bp.post("/clock-in/correction")
@permission_required("correction", "submit")
def do_correction():
    """Submit a missed-punch correction from the kiosk."""
    actor = get_current_user()
    punch_type = request.form.get("punch_type", "clock_in")
    raw_time = request.form.get("requested_time", "")
    reason = request.form.get("reason", "").strip()

    try:
        requested_time = datetime.fromisoformat(raw_time)
    except (ValueError, TypeError):
        return render_template(
            "partials/clockin_result.html", result=None, error="invalid date/time format"
        ), 400

    try:
        correction = correction_service.submit_correction(
            user_id=actor.id,
            punch_type=punch_type,
            requested_time=requested_time,
            reason=reason,
            actor_id=actor.id,
        )
    except CorrectionError as exc:
        return render_template(
            "partials/clockin_result.html", result=None, error=str(exc)
        ), 400

    return render_template(
        "partials/clockin_result.html",
        result=None,
        error=None,
        message=f"Correction #{correction.id} submitted for admin review.",
    )
