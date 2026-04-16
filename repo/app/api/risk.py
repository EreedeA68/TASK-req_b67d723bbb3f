"""Risk/fraud JSON API."""
from flask import Blueprint, jsonify

from app.core.rbac import get_current_user, permission_required
from app.services import risk_service

risk_api_bp = Blueprint("risk_api", __name__)


@risk_api_bp.get("")
@permission_required("risk", "view")
def list_flags():
    flags = risk_service.list_flags()
    return jsonify({"results": [f.to_dict() for f in flags]})


@risk_api_bp.post("/<int:user_id>/clear")
@permission_required("risk", "clear")
def clear_flags(user_id: int):
    actor = get_current_user()
    count = risk_service.clear_flags(user_id, actor_id=actor.id if actor else None)
    return jsonify({"cleared": count, "user_id": user_id})


@risk_api_bp.post("/member/<int:member_id>/clear")
@permission_required("risk", "clear")
def clear_member_flags(member_id: int):
    """Clear risk flags by member_id (used by points/stored-value abuse system)."""
    actor = get_current_user()
    count = risk_service.clear_member_flags(member_id, actor_id=actor.id if actor else None)
    return jsonify({"cleared": count, "member_id": member_id})
