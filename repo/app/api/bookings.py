"""Booking JSON API."""
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import booking_service
from app.services.booking_service import BookingAccessDenied, BookingError

bookings_api_bp = Blueprint("bookings_api", __name__)


def _parse_dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


@bookings_api_bp.post("")
@permission_required("booking", "create")
def create_booking():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()
    try:
        booking = booking_service.create_booking(
            member_id=int(data["member_id"]),
            photographer_id=int(data["photographer_id"]),
            start_time=_parse_dt(data["start_time"]),
            end_time=_parse_dt(data["end_time"]),
            actor_id=actor.id if actor else None,
        )
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"invalid input: {exc}"}), 400
    except BookingError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(booking.to_dict()), 201


@bookings_api_bp.get("")
@permission_required("booking", "view")
def list_bookings():
    actor = get_current_user()
    photographer_id = request.args.get("photographer_id", type=int)
    results = booking_service.list_bookings(
        photographer_id=photographer_id,
        actor_id=actor.id if actor else None,
    )
    return jsonify({"results": [b.to_dict() for b in results]})


@bookings_api_bp.post("/<int:booking_id>/confirm")
@permission_required("booking", "confirm", record_scope=True)
def confirm(booking_id: int):
    booking = booking_service.get_by_id(booking_id)
    if booking is None:
        return jsonify({"error": "booking not found"}), 404
    actor = get_current_user()
    try:
        booking_service.check_access(booking, actor.id if actor else None)
    except BookingAccessDenied:
        return jsonify({"error": "forbidden"}), 403
    try:
        booking = booking_service.confirm_booking(
            booking, actor_id=actor.id if actor else None
        )
    except BookingError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(booking.to_dict())


@bookings_api_bp.post("/<int:booking_id>/cancel")
@permission_required("booking", "cancel", record_scope=True)
def cancel(booking_id: int):
    booking = booking_service.get_by_id(booking_id)
    if booking is None:
        return jsonify({"error": "booking not found"}), 404
    actor = get_current_user()
    try:
        booking_service.check_access(booking, actor.id if actor else None)
    except BookingAccessDenied:
        return jsonify({"error": "forbidden"}), 403
    try:
        booking = booking_service.cancel_booking(
            booking, actor_id=actor.id if actor else None
        )
    except BookingError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(booking.to_dict())
