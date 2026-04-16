"""Photographer schedule views — HTMX list/create."""
from datetime import date, time

from flask import Blueprint, render_template, request

from app.core.rbac import get_current_user, permission_required
from app.models.role import Role
from app.models.user import User
from app.services import schedule_service
from app.services.schedule_service import ScheduleError

schedules_view_bp = Blueprint("schedules_view", __name__)


def _get_photographers():
    return User.query.join(User.roles).filter(Role.name == "photographer").all()


@schedules_view_bp.get("/schedules")
@permission_required("schedule", "view")
def schedules_page():
    schedules = schedule_service.list_schedules()
    return render_template(
        "schedules.html",
        schedules=schedules,
        photographers=_get_photographers(),
        user=get_current_user(),
        error=None,
    )


@schedules_view_bp.post("/schedules/create")
@permission_required("schedule", "create")
def do_create():
    actor = get_current_user()
    try:
        schedule_service.create_schedule(
            photographer_id=int(request.form["photographer_id"]),
            sched_date=date.fromisoformat(request.form["date"]),
            start_time=time.fromisoformat(request.form["start_time"]),
            end_time=time.fromisoformat(request.form["end_time"]),
            sched_type=request.form.get("type", "working"),
            actor_id=actor.id if actor else None,
        )
    except (KeyError, ValueError, TypeError, ScheduleError) as exc:
        schedules = schedule_service.list_schedules()
        return render_template(
            "schedules.html",
            schedules=schedules,
            photographers=_get_photographers(),
            user=actor,
            error=str(exc),
        ), 400

    schedules = schedule_service.list_schedules()
    return render_template(
        "schedules.html",
        schedules=schedules,
        photographers=_get_photographers(),
        user=actor,
        error=None,
    )


@schedules_view_bp.get("/schedules/list")
@permission_required("schedule", "view")
def schedules_list_partial():
    """HTMX partial: refreshable schedule list."""
    photographer_id = request.args.get("photographer_id", type=int)
    raw_date = request.args.get("date")
    sched_date = date.fromisoformat(raw_date) if raw_date else None
    schedules = schedule_service.list_schedules(
        photographer_id=photographer_id, sched_date=sched_date
    )
    return render_template(
        "partials/schedule_list.html", schedules=schedules
    )
