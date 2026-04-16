"""Member views — lookup page with HTMX partial rendering."""
from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.services import member_service, permission_service
from app.services.member_service import MemberError, member_to_dict

members_view_bp = Blueprint("members_view", __name__)


def _is_admin() -> bool:
    user = get_current_user()
    return user is not None and user.has_role("admin")


def _serialize(member, *, actor=None, admin=False):
    """Serialize with ABAC field-level enforcement."""
    restricted = permission_service.get_restricted_fields(actor, "member", "view")
    allowed = permission_service.get_allowed_fields(actor, "member", "view")
    return member_to_dict(
        member, is_admin=admin,
        restricted_fields=restricted, allowed_fields=allowed,
    )


@members_view_bp.get("/members")
@permission_required("member", "search")
def members_page():
    return render_template("members.html", result=None, user=get_current_user())


@members_view_bp.get("/members/lookup")
@permission_required("member", "search")
def members_lookup():
    """HTMX partial: search by phone or member_id."""
    query = (request.args.get("q") or "").strip()
    actor = get_current_user()
    actor_id = actor.id if actor else None
    admin = _is_admin()

    if not query:
        return render_template(
            "partials/member_result.html",
            query=query,
            member=None,
            extras=[],
        )

    member_dict = None
    extras: list = []
    try:
        member = member_service.lookup(query, actor_id=actor_id)
        if member is not None:
            if permission_service.check_record_access(actor, "member", "view", member.id):
                member_dict = _serialize(member, actor=actor, admin=admin)
        else:
            results = member_service.search(query, actor_id=actor_id)
            visible = [m for m in results
                       if permission_service.check_record_access(actor, "member", "view", m.id)]
            extras = [_serialize(m, actor=actor, admin=admin) for m in visible]
    except MemberError:
        member_dict = None
        extras = []

    return render_template(
        "partials/member_result.html",
        query=query,
        member=member_dict,
        extras=extras,
    )
