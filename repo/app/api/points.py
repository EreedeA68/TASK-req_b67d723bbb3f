"""Points economy JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import points_service
from app.services.points_service import PointsError

points_api_bp = Blueprint("points_api", __name__)


@points_api_bp.post("/redeem")
@permission_required("order", "pay")
def redeem_points():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()

    for field in ("member_id", "order_id", "points"):
        if field not in data or data.get(field) in (None, ""):
            return jsonify({"error": f"{field} is required"}), 400

    try:
        member_id = int(data["member_id"])
        order_id = int(data["order_id"])
        pts = int(data["points"])
    except (TypeError, ValueError):
        return jsonify({"error": "member_id, order_id, and points must be integers"}), 400

    # Record-scope checks on both the member and the order being modified.
    from app.services import permission_service
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403
    if not permission_service.check_record_access(actor, "order", "pay", order_id):
        return jsonify({"error": "forbidden"}), 403

    # Resolve order server-side — never trust client-supplied subtotal
    from app.services import order_service
    order = order_service.get_by_id(order_id, check_expiry=False)
    if order is None:
        return jsonify({"error": "order not found"}), 404
    if order.member_id != member_id:
        return jsonify({"error": "order does not belong to this member"}), 400
    if order.status not in ("created", "paid"):
        return jsonify({"error": "order is not in a redeemable state"}), 400
    order_subtotal = order.subtotal

    try:
        entry = points_service.redeem_points(
            member_id=member_id,
            order_id=order_id,
            points_to_redeem=pts,
            order_subtotal=order_subtotal,
            actor_id=actor.id if actor else None,
        )
    except PointsError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(entry.to_dict()), 200


@points_api_bp.get("/balance/<int:member_id>")
@permission_required("member", "view")
def get_balance(member_id: int):
    from app.services import permission_service
    actor = get_current_user()
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403
    balance = points_service.get_balance(member_id)
    return jsonify({"member_id": member_id, "balance": balance})


@points_api_bp.get("/history/<int:member_id>")
@permission_required("member", "view")
def get_history(member_id: int):
    from app.services import permission_service
    actor = get_current_user()
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403
    entries = points_service.get_history(member_id)
    return jsonify({"results": [e.to_dict() for e in entries]})
