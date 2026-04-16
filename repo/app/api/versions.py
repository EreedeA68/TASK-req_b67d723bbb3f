"""Versioning JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import versioning_service
from app.services.versioning_service import VersioningError

versions_api_bp = Blueprint("versions_api", __name__)


@versions_api_bp.get("")
@permission_required("versioning", "view")
def list_versions():
    entity_type = request.args.get("entity_type", "")
    entity_id = request.args.get("entity_id", type=int)
    if not entity_type or entity_id is None:
        return jsonify({"error": "entity_type and entity_id query params required"}), 400
    versions = versioning_service.list_versions(entity_type, entity_id)
    return jsonify({"results": [v.to_dict() for v in versions]})


@versions_api_bp.post("/<entity_type>/<int:entity_id>/snapshot")
@permission_required("versioning", "snapshot")
def snapshot(entity_type: str, entity_id: int):
    actor = get_current_user()
    try:
        version = versioning_service.create_snapshot(
            entity_type, entity_id, actor_id=actor.id if actor else None
        )
    except VersioningError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(version.to_dict()), 201


@versions_api_bp.post("/<entity_type>/<int:entity_id>/rollback")
@permission_required("versioning", "rollback")
def rollback(entity_type: str, entity_id: int):
    actor = get_current_user()
    try:
        snap = versioning_service.rollback(
            entity_type, entity_id, actor_id=actor.id if actor else None
        )
    except VersioningError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"restored": snap})
