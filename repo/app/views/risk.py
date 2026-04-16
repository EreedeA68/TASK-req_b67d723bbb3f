"""Risk/fraud views."""
from flask import Blueprint, render_template

from app.core.rbac import get_current_user, permission_required
from app.services import risk_service

risk_view_bp = Blueprint("risk_view", __name__)


@risk_view_bp.get("/risk")
@permission_required("risk", "view")
def risk_page():
    flags = risk_service.list_flags()
    return render_template("risk.html", flags=flags, user=get_current_user())


@risk_view_bp.post("/risk/<int:user_id>/clear")
@permission_required("risk", "clear")
def do_clear(user_id: int):
    actor = get_current_user()
    risk_service.clear_flags(user_id, actor_id=actor.id if actor else None)
    flags = risk_service.list_flags()
    return render_template("partials/risk_list.html", flags=flags)


@risk_view_bp.post("/risk/member/<int:member_id>/clear")
@permission_required("risk", "clear")
def do_clear_member(member_id: int):
    actor = get_current_user()
    risk_service.clear_member_flags(member_id, actor_id=actor.id if actor else None)
    flags = risk_service.list_flags()
    return render_template("partials/risk_list.html", flags=flags)
