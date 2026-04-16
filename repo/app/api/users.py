"""User and role management JSON API (admin-only)."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import auth_service
from app.services.auth_service import AuthError

users_api_bp = Blueprint("users_api", __name__)


@users_api_bp.get("")
@permission_required("user", "view")
def list_users():
    users = auth_service.list_users()
    return jsonify({"results": [u.to_dict() for u in users]})


@users_api_bp.put("/<int:user_id>/roles")
@permission_required("user", "manage")
def assign_roles(user_id: int):
    """Replace the user's roles with the provided list."""
    data = request.get_json(silent=True) or {}
    roles = data.get("roles")
    if not isinstance(roles, list):
        return jsonify({"error": "roles must be a list"}), 400
    actor = get_current_user()
    try:
        user = auth_service.assign_roles(
            user_id, roles, actor_id=actor.id if actor else None,
        )
    except AuthError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg else 400
        return jsonify({"error": msg}), status
    return jsonify(user.to_dict())


@users_api_bp.post("/<int:user_id>/roles")
@permission_required("user", "manage")
def add_role(user_id: int):
    """Add a single role to the user."""
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if not role or not isinstance(role, str):
        return jsonify({"error": "role is required"}), 400
    actor = get_current_user()
    try:
        user = auth_service.add_role(
            user_id, role, actor_id=actor.id if actor else None,
        )
    except AuthError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg else 400
        return jsonify({"error": msg}), status
    return jsonify(user.to_dict())


@users_api_bp.delete("/<int:user_id>/roles/<string:role>")
@permission_required("user", "manage")
def remove_role(user_id: int, role: str):
    """Remove a role from the user."""
    actor = get_current_user()
    try:
        user = auth_service.remove_role(
            user_id, role, actor_id=actor.id if actor else None,
        )
    except AuthError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg else 400
        return jsonify({"error": msg}), status
    return jsonify(user.to_dict())
