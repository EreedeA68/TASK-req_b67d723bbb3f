"""Stored-value JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import stored_value_service
from app.services.stored_value_service import StoredValueError

stored_value_api_bp = Blueprint("stored_value_api", __name__)


@stored_value_api_bp.post("/credit")
@permission_required("order", "create")
def credit_balance():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()

    for field in ("member_id", "amount"):
        if field not in data or data.get(field) in (None, ""):
            return jsonify({"error": f"{field} is required"}), 400

    try:
        member_id = int(data["member_id"])
        amount = float(data["amount"])
    except (TypeError, ValueError):
        return jsonify({"error": "member_id must be integer and amount must be numeric"}), 400

    # Record-scope: only allow crediting members within the actor's scope.
    from app.services import permission_service
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403

    description = data.get("description")

    try:
        entry = stored_value_service.credit(
            member_id=member_id,
            amount=amount,
            description=description,
            actor_id=actor.id if actor else None,
        )
    except StoredValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(entry.to_dict()), 200


@stored_value_api_bp.post("/debit")
@permission_required("order", "create")
def debit_balance():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()

    for field in ("member_id", "amount"):
        if field not in data or data.get(field) in (None, ""):
            return jsonify({"error": f"{field} is required"}), 400

    try:
        member_id = int(data["member_id"])
        amount = float(data["amount"])
    except (TypeError, ValueError):
        return jsonify({"error": "member_id must be integer and amount must be numeric"}), 400

    # Record-scope: only allow debiting members within the actor's scope.
    from app.services import permission_service
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403

    order_id = data.get("order_id")
    if order_id is not None:
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return jsonify({"error": "order_id must be an integer"}), 400

    try:
        entry = stored_value_service.debit(
            member_id=member_id,
            amount=amount,
            order_id=order_id,
            actor_id=actor.id if actor else None,
        )
    except StoredValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(entry.to_dict()), 200


def _can_see_raw_balance(actor) -> bool:
    """Raw stored-value balances require admin role or explicit field grant.

    Default behavior (no grant) masks balances for non-admin roles.  An
    admin can unmask by granting a ScopePermission(scope_type="field",
    scope_value="stored_value_balance") to the role.
    """
    if actor is None:
        return False
    if actor.has_role("admin"):
        return True
    from app.models.scope_permission import ScopePermission
    role_names = actor.role_names()
    grant = ScopePermission.query.filter(
        ScopePermission.role_name.in_(role_names),
        ScopePermission.resource == "member",
        ScopePermission.action == "view",
        ScopePermission.scope_type == "field",
        ScopePermission.scope_value == "stored_value_balance",
        ScopePermission.granted.is_(True),
    ).first()
    return grant is not None


def _mask_amount(amount):
    """Mask a numeric balance to '****' for unauthorized viewers."""
    return "****" if amount is not None else None


@stored_value_api_bp.get("/balance/<int:member_id>")
@permission_required("member", "view")
def get_balance(member_id: int):
    from app.services import permission_service
    actor = get_current_user()
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403
    balance = stored_value_service.get_balance(member_id)
    if not _can_see_raw_balance(actor):
        balance = _mask_amount(balance)
    return jsonify({"member_id": member_id, "balance": balance})


@stored_value_api_bp.get("/history/<int:member_id>")
@permission_required("member", "view")
def get_history(member_id: int):
    from app.services import permission_service
    actor = get_current_user()
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403
    entries = stored_value_service.get_history(member_id)
    can_raw = _can_see_raw_balance(actor)

    # Compute running balance chronologically so each row exposes the
    # balance_after the ledger entry is applied.
    chronological = sorted(entries, key=lambda e: e.created_at)
    running = 0.0
    balances: dict[int, float] = {}
    for e in chronological:
        running += e.amount if e.type == "credit" else -e.amount
        balances[e.id] = round(running, 2)

    results = []
    for e in entries:  # preserve service-supplied order (newest first)
        d = e.to_dict()
        d["balance_after"] = balances.get(e.id, 0.0)
        if not can_raw:
            d["amount"] = _mask_amount(d.get("amount"))
            d["balance_after"] = _mask_amount(d.get("balance_after"))
        results.append(d)
    return jsonify({"results": results})
