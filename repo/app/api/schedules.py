"""Photographer scheduling JSON API."""
from datetime import date, time

from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, permission_required
from app.services import schedule_service
from app.services.schedule_service import ScheduleError

schedules_api_bp = Blueprint("schedules_api", __name__)


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _parse_time(raw: str) -> time:
    return time.fromisoformat(raw)


@schedules_api_bp.post("")
@permission_required("schedule", "create")
def create_schedule():
    data = request.get_json(silent=True) or {}
    actor = get_current_user()
    try:
        sched = schedule_service.create_schedule(
            photographer_id=int(data["photographer_id"]),
            sched_date=_parse_date(data["date"]),
            start_time=_parse_time(data["start_time"]),
            end_time=_parse_time(data["end_time"]),
            sched_type=data.get("type", "working"),
            actor_id=actor.id if actor else None,
        )
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"invalid input: {exc}"}), 400
    except ScheduleError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(sched.to_dict()), 201


@schedules_api_bp.get("")
@permission_required("schedule", "view")
def list_schedules():
    photographer_id = request.args.get("photographer_id", type=int)
    sched_date = None
    raw_date = request.args.get("date")
    if raw_date:
        try:
            sched_date = _parse_date(raw_date)
        except ValueError:
            return jsonify({"error": "invalid date format"}), 400
    results = schedule_service.list_schedules(
        photographer_id=photographer_id,
        sched_date=sched_date,
    )
    return jsonify({"results": [s.to_dict() for s in results]})
