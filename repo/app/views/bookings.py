"""Booking views — HTMX create/list/confirm/cancel."""
from datetime import datetime

from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.models.member import Member
from app.models.role import Role
from app.models.user import User
from app.services import booking_service
from app.services.booking_service import BookingAccessDenied, BookingError

bookings_view_bp = Blueprint("bookings_view", __name__)


def _get_photographers():
    return User.query.join(User.roles).filter(Role.name == "photographer").all()


@bookings_view_bp.get("/bookings")
@permission_required("booking", "view")
def bookings_page():
    actor = get_current_user()
    bookings = booking_service.list_bookings(actor_id=actor.id if actor else None)
    members = Member.query.order_by(Member.name).limit(200).all()
    return render_template(
        "bookings.html",
        bookings=bookings,
        members=members,
        photographers=_get_photographers(),
        user=actor,
        error=None,
    )


@bookings_view_bp.post("/bookings/create")
@permission_required("booking", "create")
def do_create():
    actor = get_current_user()
    try:
        booking_service.create_booking(
            member_id=int(request.form["member_id"]),
            photographer_id=int(request.form["photographer_id"]),
            start_time=datetime.fromisoformat(request.form["start_time"]),
            end_time=datetime.fromisoformat(request.form["end_time"]),
            actor_id=actor.id if actor else None,
        )
    except (KeyError, ValueError, TypeError, BookingError) as exc:
        bookings = booking_service.list_bookings(actor_id=actor.id if actor else None)
        members = Member.query.order_by(Member.name).limit(200).all()
        return render_template(
            "bookings.html",
            bookings=bookings,
            members=members,
            photographers=_get_photographers(),
            user=actor,
            error=str(exc),
        ), 400

    bookings = booking_service.list_bookings(actor_id=actor.id if actor else None)
    members = Member.query.order_by(Member.name).limit(200).all()
    return render_template(
        "bookings.html",
        bookings=bookings,
        members=members,
        photographers=_get_photographers(),
        user=actor,
        error=None,
    )


@bookings_view_bp.post("/bookings/<int:booking_id>/confirm")
@permission_required("booking", "confirm", record_scope=True)
def do_confirm(booking_id: int):
    booking = booking_service.get_by_id(booking_id)
    if booking is None:
        return render_template("partials/booking_error.html", error="booking not found"), 404
    actor = get_current_user()
    try:
        booking_service.check_access(booking, actor.id if actor else None)
    except BookingAccessDenied:
        return render_template("partials/booking_error.html", error="forbidden"), 403
    try:
        booking = booking_service.confirm_booking(
            booking, actor_id=actor.id if actor else None
        )
    except BookingError as exc:
        return render_template("partials/booking_error.html", error=str(exc)), 400
    return render_template("partials/booking_row.html", booking=booking)


@bookings_view_bp.post("/bookings/<int:booking_id>/cancel")
@permission_required("booking", "cancel", record_scope=True)
def do_cancel(booking_id: int):
    booking = booking_service.get_by_id(booking_id)
    if booking is None:
        return render_template("partials/booking_error.html", error="booking not found"), 404
    actor = get_current_user()
    try:
        booking_service.check_access(booking, actor.id if actor else None)
    except BookingAccessDenied:
        return render_template("partials/booking_error.html", error="forbidden"), 403
    try:
        booking = booking_service.cancel_booking(
            booking, actor_id=actor.id if actor else None
        )
    except BookingError as exc:
        return render_template("partials/booking_error.html", error=str(exc)), 400
    return render_template("partials/booking_row.html", booking=booking)


@bookings_view_bp.get("/bookings/list")
@permission_required("booking", "view")
def bookings_list_partial():
    """HTMX partial: refreshable booking list."""
    actor = get_current_user()
    bookings = booking_service.list_bookings(actor_id=actor.id if actor else None)
    return render_template("partials/booking_list.html", bookings=bookings)
