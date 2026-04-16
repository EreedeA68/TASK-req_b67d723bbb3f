"""Versioning views."""
from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.services import versioning_service
from app.services.versioning_service import VersioningError

versions_view_bp = Blueprint("versions_view", __name__)


@versions_view_bp.get("/versions")
@permission_required("versioning", "view")
def versions_page():
    return render_template("versions.html", user=get_current_user(), versions=[], error=None)


@versions_view_bp.post("/versions/snapshot")
@permission_required("versioning", "snapshot")
def do_snapshot():
    actor = get_current_user()
    entity_type = request.form.get("entity_type", "")
    try:
        entity_id = int(request.form.get("entity_id", 0))
    except (TypeError, ValueError):
        return render_template("versions.html", user=actor, versions=[], error="invalid entity_id"), 400
    try:
        versioning_service.create_snapshot(entity_type, entity_id, actor_id=actor.id)
    except VersioningError as exc:
        return render_template("versions.html", user=actor, versions=[], error=str(exc)), 400
    versions = versioning_service.list_versions(entity_type, entity_id)
    return render_template("versions.html", user=actor, versions=versions, error=None)
