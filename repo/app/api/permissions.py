"""Permissions management JSON API — admin only."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import permission_service

permissions_api_bp = Blueprint("permissions_api", __name__)


@permissions_api_bp.get("")
@permission_required("permission", "view")
def list_permissions():
    role_name = request.args.get("role_name")
    perms = permission_service.list_permissions(role_name=role_name)
    return jsonify({"results": [p.to_dict() for p in perms]})


@permissions_api_bp.post("")
@permission_required("permission", "manage")
def grant_permission():
    data = request.get_json(silent=True) or {}
    role_name = data.get("role_name")
    resource = data.get("resource")
    action = data.get("action")

    if not role_name or not resource or not action:
        return jsonify({"error": "role_name, resource, and action are required"}), 400

    actor = get_current_user()
    perm = permission_service.grant_permission(
        role_name=role_name,
        resource=resource,
        action=action,
        scope_type=data.get("scope_type"),
        scope_value=data.get("scope_value"),
        actor_id=actor.id if actor else None,
    )
    return jsonify(perm.to_dict()), 201


@permissions_api_bp.delete("/<int:perm_id>")
@permission_required("permission", "manage")
def revoke_permission(perm_id: int):
    actor = get_current_user()
    deleted = permission_service.revoke_permission(
        perm_id, actor_id=actor.id if actor else None,
    )
    if not deleted:
        return jsonify({"error": "permission not found"}), 404
    return jsonify({"deleted": True, "id": perm_id})
