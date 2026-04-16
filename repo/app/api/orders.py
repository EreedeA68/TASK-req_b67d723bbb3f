"""Orders JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import order_service
from app.services.order_service import OrderAccessDenied, OrderError

orders_api_bp = Blueprint("orders_api", __name__)


@orders_api_bp.post("")
@permission_required("order", "create")
def create_order():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()

    if "member_id" not in data or data.get("member_id") in (None, ""):
        return jsonify({"error": "member_id is required"}), 400
    if "subtotal" not in data or data.get("subtotal") in (None, ""):
        return jsonify({"error": "subtotal is required"}), 400

    try:
        member_id = int(data.get("member_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "member_id must be an integer"}), 400

    try:
        order = order_service.create_order(
            member_id=member_id,
            subtotal=data.get("subtotal"),
            discount=data.get("discount") or 0.0,
            items=data.get("items"),
            actor_id=actor.id if actor else None,
        )
    except OrderError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(order.to_dict()), 201


@orders_api_bp.get("/<int:order_id>")
@permission_required("order", "view", record_scope=True)
def get_order(order_id: int):
    order = order_service.get_by_id(order_id)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    actor = get_current_user()
    try:
        order_service.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(order.to_dict())


@orders_api_bp.post("/<int:order_id>/pay")
@permission_required("order", "pay", record_scope=True)
def pay_order(order_id: int):
    order = order_service.get_by_id(order_id)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    actor = get_current_user()
    try:
        order_service.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    redeem_pts = data.get("redeem_points", 0)
    try:
        redeem_pts = int(redeem_pts) if redeem_pts else 0
    except (TypeError, ValueError):
        redeem_pts = 0

    try:
        order = order_service.pay(
            order, redeem_points=redeem_pts, actor_id=actor.id if actor else None
        )
    except OrderError as exc:
        return jsonify({"error": str(exc)}), 400
    result = order.to_dict()
    redeem_error = getattr(order, "_redeem_error", None)
    if redeem_error:
        result["redeem_warning"] = redeem_error
    return jsonify(result)


@orders_api_bp.get("/<int:order_id>/receipt")
@permission_required("order", "view", record_scope=True)
def get_receipt(order_id: int):
    order = order_service.get_by_id(order_id)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    actor = get_current_user()
    try:
        order_service.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return jsonify({"error": "forbidden"}), 403
    if not order.receipt:
        return jsonify({"error": "no receipt for this order"}), 404
    return jsonify(order.receipt.to_dict())


@orders_api_bp.get("/<int:order_id>/receipt/print")
@permission_required("order", "view", record_scope=True)
def print_receipt(order_id: int):
    """Return a plain-text printable receipt payload.

    Offline operation: the payload is returned as text/plain so the staff
    terminal can hand it off to a local thermal printer via the browser's
    print dialog or a kiosk print helper.  No external print service is
    invoked.
    """
    from flask import Response
    from app.services import order_service as _os

    order = _os.get_by_id(order_id)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    actor = get_current_user()
    try:
        _os.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return jsonify({"error": "forbidden"}), 403
    if not order.receipt:
        return jsonify({"error": "no receipt for this order"}), 404

    r = order.receipt
    lines = [
        "==== WildLifeLens Gift Shop ====",
        f"Order #{order.id}",
        f"Member: {order.member.name} ({order.member.member_id})",
        f"Date: {r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else ''}",
        "--------------------------------",
        f"Subtotal:        ${r.subtotal:>9.2f}",
        f"Discount:       -${r.discount:>9.2f}",
    ]
    if r.points_redeemed > 0:
        lines.append(
            f"Points redeemed: {r.points_redeemed} (-${r.points_value:>7.2f})"
        )
    lines.extend([
        "--------------------------------",
        f"TOTAL:           ${r.total:>9.2f}",
        "",
        f"Points earned:   {r.points_earned}",
    ])
    if r.note:
        lines.append(f"Note: {r.note}")
    lines.extend(["", "Thank you for visiting!", "================================"])

    return Response("\n".join(lines), mimetype="text/plain")


@orders_api_bp.post("/<int:order_id>/advance")
@permission_required("order", "advance", record_scope=True)
def advance_order(order_id: int):
    order = order_service.get_by_id(order_id)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    actor = get_current_user()
    try:
        order_service.check_access(order, actor.id if actor else None)
    except OrderAccessDenied:
        return jsonify({"error": "forbidden"}), 403
    try:
        order = order_service.advance(order, actor_id=actor.id if actor else None)
    except OrderError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(order.to_dict())
