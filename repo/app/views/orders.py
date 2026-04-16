"""Order views — creation page, detail page, HTMX status actions."""
from flask import Blueprint, redirect, render_template, request, url_for

from app.core.rbac import get_current_user, permission_required
from app.models.member import Member
from app.services import member_service, order_service
from app.services.order_service import OrderAccessDenied, OrderError


def _serialize_members_for_picker(members, actor):
    """Return dicts with masked phone for non-admin actors.

    Filters out members the actor cannot access per record-level ABAC scope
    so the order-create dropdown only surfaces members the staff user is
    authorized to transact on.
    """
    from app.services import permission_service
    is_admin = actor is not None and actor.has_role("admin")
    allowed = permission_service.get_allowed_fields(actor, "member", "view")
    visible = [
        m for m in members
        if permission_service.check_record_access(actor, "member", "view", m.id)
    ]
    return [
        member_service.member_to_dict(m, is_admin=is_admin, allowed_fields=allowed)
        for m in visible
    ]

orders_view_bp = Blueprint("orders_view", __name__)


def _render_order_error_partial(message: str, status: int = 400):
    """Always return a partial from HTMX endpoints, even when order is missing."""
    return render_template(
        "partials/order_error.html", error=message
    ), status


@orders_view_bp.get("/orders/create")
@permission_required("order", "create")
def create_page():
    members = _serialize_members_for_picker(
        Member.query.order_by(Member.name).limit(200).all(),
        get_current_user(),
    )
    return render_template(
        "order_create.html",
        members=members,
        error=None,
        user=get_current_user(),
    )


@orders_view_bp.post("/orders/create")
@permission_required("order", "create")
def do_create():
    actor = get_current_user()
    raw_member_id = request.form.get("member_id")
    raw_subtotal = request.form.get("subtotal")

    if not raw_member_id:
        members = _serialize_members_for_picker(
        Member.query.order_by(Member.name).limit(200).all(),
        get_current_user(),
    )
        return render_template(
            "order_create.html",
            members=members,
            error="member_id is required",
            user=actor,
        ), 400
    if raw_subtotal in (None, ""):
        members = _serialize_members_for_picker(
        Member.query.order_by(Member.name).limit(200).all(),
        get_current_user(),
    )
        return render_template(
            "order_create.html",
            members=members,
            error="subtotal is required",
            user=actor,
        ), 400

    try:
        member_id = int(raw_member_id)
        subtotal = float(raw_subtotal)
    except (TypeError, ValueError):
        members = _serialize_members_for_picker(
        Member.query.order_by(Member.name).limit(200).all(),
        get_current_user(),
    )
        return render_template(
            "order_create.html",
            members=members,
            error="invalid input",
            user=actor,
        ), 400

    try:
        order = order_service.create_order(
            member_id=member_id,
            subtotal=subtotal,
            discount=float(request.form.get("discount") or 0),
            actor_id=actor.id if actor else None,
        )
    except OrderError as exc:
        members = _serialize_members_for_picker(
        Member.query.order_by(Member.name).limit(200).all(),
        get_current_user(),
    )
        return render_template(
            "order_create.html",
            members=members,
            error=str(exc),
            user=actor,
        ), 400
    return redirect(url_for("orders_view.order_detail", order_id=order.id))


@orders_view_bp.get("/orders/<int:order_id>")
@permission_required("order", "view", record_scope=True)
def order_detail(order_id: int):
    order = order_service.get_by_id(order_id)
    if order is None:
        return "Order not found", 404
    actor = get_current_user()
    try:
        order_service.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return ("Forbidden", 403)
    return render_template(
        "order_detail.html",
        order=order,
        member=order.member,
        user=actor,
    )


@orders_view_bp.post("/orders/<int:order_id>/pay")
@permission_required("order", "pay", record_scope=True)
def do_pay(order_id: int):
    order = order_service.get_by_id(order_id)
    if order is None:
        return _render_order_error_partial("order not found", 404)
    actor = get_current_user()
    try:
        order_service.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return _render_order_error_partial("forbidden", 403)
    raw_redeem = request.form.get("redeem_points", "0")
    try:
        redeem_pts = int(raw_redeem) if raw_redeem else 0
    except (TypeError, ValueError):
        redeem_pts = 0

    try:
        order = order_service.pay(
            order, redeem_points=redeem_pts,
            actor_id=actor.id if actor else None,
        )
    except OrderError as exc:
        return render_template(
            "partials/order_status.html",
            order=order,
            error=str(exc),
        ), 400
    redeem_error = getattr(order, "_redeem_error", None)
    return render_template("partials/order_status.html", order=order, error=redeem_error)


@orders_view_bp.post("/orders/<int:order_id>/advance")
@permission_required("order", "advance", record_scope=True)
def do_advance(order_id: int):
    order = order_service.get_by_id(order_id)
    if order is None:
        return _render_order_error_partial("order not found", 404)
    actor = get_current_user()
    try:
        order_service.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return _render_order_error_partial("forbidden", 403)
    try:
        order = order_service.advance(
            order, actor_id=actor.id if actor else None
        )
    except OrderError as exc:
        return render_template(
            "partials/order_status.html",
            order=order,
            error=str(exc),
        ), 400
    return render_template("partials/order_status.html", order=order, error=None)
