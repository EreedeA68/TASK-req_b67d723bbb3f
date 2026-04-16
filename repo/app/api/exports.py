"""Export JSON API."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import export_service
from app.services.export_service import ExportError

exports_api_bp = Blueprint("exports_api", __name__)


@exports_api_bp.post("")
@permission_required("export", "create")
def create_export():
    data = request.get_json(silent=True) or {}
    export_type = data.get("type", "")
    actor = get_current_user()
    is_admin = actor is not None and actor.has_role("admin")
    try:
        job = export_service.create_export(
            export_type,
            actor_id=actor.id if actor else None,
            is_admin=is_admin,
        )
    except ExportError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(job.to_dict()), 201


@exports_api_bp.get("")
@permission_required("export", "view")
def list_exports():
    actor = get_current_user()
    is_admin = actor is not None and actor.has_role("admin")
    jobs = export_service.list_exports(
        actor_id=actor.id if actor else None,
        is_admin=is_admin,
    )
    return jsonify({"results": [j.to_dict() for j in jobs]})
