"""Export views."""
from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.services import export_service
from app.services.export_service import ExportError

exports_view_bp = Blueprint("exports_view", __name__)


def _scoped_jobs(actor):
    return export_service.list_exports(
        actor_id=actor.id if actor else None,
        is_admin=actor is not None and actor.has_role("admin"),
    )


@exports_view_bp.get("/exports")
@permission_required("export", "view")
def exports_page():
    actor = get_current_user()
    jobs = _scoped_jobs(actor)
    return render_template("exports.html", jobs=jobs, user=actor, error=None)


@exports_view_bp.post("/exports/create")
@permission_required("export", "create")
def do_create():
    actor = get_current_user()
    export_type = request.form.get("type", "")
    is_admin = actor is not None and actor.has_role("admin")
    try:
        export_service.create_export(
            export_type,
            actor_id=actor.id if actor else None,
            is_admin=is_admin,
        )
    except ExportError as exc:
        jobs = _scoped_jobs(actor)
        return render_template(
            "exports.html", jobs=jobs, user=actor, error=str(exc),
        ), 400
    jobs = _scoped_jobs(actor)
    return render_template("exports.html", jobs=jobs, user=actor, error=None)
