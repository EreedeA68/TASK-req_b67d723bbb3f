"""Members JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import member_service, permission_service
from app.services.member_service import MemberError, member_to_dict

members_api_bp = Blueprint("members_api", __name__)


def _is_admin() -> bool:
    user = get_current_user()
    return user is not None and user.has_role("admin")


def _serialize(member, *, actor=None, admin=False):
    """Serialize a member with ABAC field-level enforcement.

    - restricted_fields: for admin — honors admin-side restrictions (rare)
    - allowed_fields: for non-admin — explicit field grants unmask
    """
    restricted = permission_service.get_restricted_fields(actor, "member", "view")
    allowed = permission_service.get_allowed_fields(actor, "member", "view")
    return member_to_dict(
        member, is_admin=admin,
        restricted_fields=restricted, allowed_fields=allowed,
    )


@members_api_bp.get("/search")
@permission_required("member", "search")
def search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "query 'q' must not be empty"}), 400
    actor = get_current_user()
    actor_id = actor.id if actor else None
    admin = _is_admin()

    try:
        exact = member_service.lookup(query, actor_id=actor_id)
    except MemberError as exc:
        return jsonify({"error": str(exc)}), 400
    if exact is not None:
        if not permission_service.check_record_access(actor, "member", "view", exact.id):
            return jsonify({"error": "forbidden"}), 403
        return jsonify({"results": [_serialize(exact, actor=actor, admin=admin)], "match": "exact"})

    try:
        results = member_service.search(query, actor_id=actor_id)
    except MemberError as exc:
        return jsonify({"error": str(exc)}), 400
    # Filter results by record-level scope
    visible = [m for m in results
                if permission_service.check_record_access(actor, "member", "view", m.id)]
    return jsonify(
        {"results": [_serialize(m, actor=actor, admin=admin) for m in visible], "match": "partial"}
    )


@members_api_bp.get("/<int:member_id>")
@permission_required("member", "view")
def get_member(member_id: int):
    member = member_service.get_by_id(member_id)
    if member is None:
        return jsonify({"error": "member not found"}), 404
    actor = get_current_user()
    if not permission_service.check_record_access(actor, "member", "view", member_id):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(_serialize(member, actor=actor, admin=_is_admin()))


@members_api_bp.post("")
@permission_required("member", "create")
def create_member():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()
    try:
        member = member_service.create_member(
            name=data.get("name") or "",
            phone_number=data.get("phone_number") or "",
            tier=(data.get("tier") or "standard"),
            member_id=data.get("member_id"),
            stored_value_balance=data.get("stored_value_balance", "0"),
            actor_id=actor.id if actor else None,
        )
    except MemberError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(member_to_dict(member, is_admin=_is_admin())), 201
