"""Photographer scheduling service."""
from datetime import date, time

from sqlalchemy import and_

from app.db import db
from app.models.schedule import PhotographerSchedule
from app.models.user import User
from app.services import audit_service


class ScheduleError(Exception):
    """Error in scheduling operations."""


VALID_TYPES = {"working", "break", "off"}


def _validate_inputs(
    photographer_id: int,
    sched_date: date,
    start: time,
    end: time,
    sched_type: str,
) -> None:
    if photographer_id is None:
        raise ScheduleError("photographer_id is required")
    if sched_date is None:
        raise ScheduleError("date is required")
    if start is None or end is None:
        raise ScheduleError("start_time and end_time are required")
    if start >= end:
        raise ScheduleError("start_time must be before end_time")
    if sched_type not in VALID_TYPES:
        raise ScheduleError(f"type must be one of {sorted(VALID_TYPES)}")
    photographer = db.session.get(User, photographer_id)
    if photographer is None:
        raise ScheduleError("photographer not found")
    if not photographer.has_role("photographer"):
        raise ScheduleError("user is not a photographer")


def _has_overlap(
    photographer_id: int,
    sched_date: date,
    start: time,
    end: time,
    exclude_id: int | None = None,
) -> bool:
    """Check if there is an overlapping schedule for the same photographer
    on the same day."""
    query = PhotographerSchedule.query.filter(
        and_(
            PhotographerSchedule.photographer_id == photographer_id,
            PhotographerSchedule.date == sched_date,
            PhotographerSchedule.start_time < end,
            PhotographerSchedule.end_time > start,
        )
    )
    if exclude_id is not None:
        query = query.filter(PhotographerSchedule.id != exclude_id)
    return query.first() is not None


def create_schedule(
    *,
    photographer_id: int,
    sched_date: date,
    start_time: time,
    end_time: time,
    sched_type: str = "working",
    actor_id: int | None = None,
) -> PhotographerSchedule:
    _validate_inputs(photographer_id, sched_date, start_time, end_time, sched_type)

    if _has_overlap(photographer_id, sched_date, start_time, end_time):
        audit_service.log(
            actor_id=actor_id,
            action="schedule_overlap_rejected",
            resource=f"photographer:{photographer_id}",
            metadata={
                "date": sched_date.isoformat(),
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        )
        raise ScheduleError(
            "overlapping schedule exists for this photographer on the same day"
        )

    schedule = PhotographerSchedule(
        photographer_id=photographer_id,
        date=sched_date,
        start_time=start_time,
        end_time=end_time,
        type=sched_type,
    )
    db.session.add(schedule)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="schedule_created",
        resource=f"schedule:{schedule.id}",
        metadata={
            "photographer_id": photographer_id,
            "date": sched_date.isoformat(),
        },
    )
    return schedule


def list_schedules(
    *,
    photographer_id: int | None = None,
    sched_date: date | None = None,
) -> list[PhotographerSchedule]:
    query = PhotographerSchedule.query
    if photographer_id is not None:
        query = query.filter_by(photographer_id=photographer_id)
    if sched_date is not None:
        query = query.filter_by(date=sched_date)
    return query.order_by(
        PhotographerSchedule.date, PhotographerSchedule.start_time
    ).all()
