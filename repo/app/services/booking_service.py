"""Booking service with conflict detection and lock mechanism."""
from datetime import datetime, timedelta

from sqlalchemy import and_, or_

from app.db import db
from app.models.booking import Booking
from app.models.member import Member
from app.models.user import User
from app.services import audit_service


class BookingError(Exception):
    """Error in booking operations."""


class BookingAccessDenied(BookingError):
    """Object-level access denied."""


def check_access(booking: "Booking", actor_id: int | None) -> None:
    """Enforce object-level ownership on bookings.

    Admin and staff may access any booking (operational workflow).
    Photographers may only access bookings assigned to them or that they created.
    Other roles are restricted to bookings they created.

    Raises BookingAccessDenied if the actor lacks access.
    Must be called from both API and view layers before mutations.
    """
    if booking is None or actor_id is None:
        raise BookingAccessDenied("forbidden")
    from app.db import db as _db
    from app.models.user import User

    actor = _db.session.get(User, actor_id)
    if actor is None:
        raise BookingAccessDenied("forbidden")
    if actor.has_role("admin") or actor.has_role("staff"):
        return
    if booking.photographer_id == actor_id:
        return
    if booking.created_by is not None and booking.created_by == actor_id:
        return
    raise BookingAccessDenied("forbidden")


LOCK_DURATION_MINUTES = 5


def _validate_times(start: datetime, end: datetime) -> None:
    if start is None or end is None:
        raise BookingError("start_time and end_time are required")
    if start >= end:
        raise BookingError("start_time must be before end_time")


def _has_conflict(
    photographer_id: int,
    start: datetime,
    end: datetime,
    exclude_id: int | None = None,
) -> Booking | None:
    """Return the first conflicting booking (confirmed OR locked-and-not-expired)
    or None.  Expired locks are ignored."""
    now = datetime.utcnow()
    query = Booking.query.filter(
        and_(
            Booking.photographer_id == photographer_id,
            Booking.start_time < end,
            Booking.end_time > start,
            or_(
                Booking.status == "confirmed",
                and_(
                    Booking.status == "locked",
                    Booking.lock_expires_at > now,
                ),
            ),
        )
    )
    if exclude_id is not None:
        query = query.filter(Booking.id != exclude_id)
    return query.first()


def _validate_schedule(
    photographer_id: int,
    start_time: datetime,
    end_time: datetime,
) -> None:
    """Validate that the booking falls within the photographer's working schedule.

    Checks:
    1. A "working" schedule entry must cover the entire booking window.
    2. No "break" or "off" schedule entry may overlap the booking window.

    If no schedule entries exist for the date the booking is allowed
    (schedule not yet configured).
    """
    from app.models.schedule import PhotographerSchedule

    booking_date = start_time.date()
    booking_start = start_time.time()
    booking_end = end_time.time()

    entries = PhotographerSchedule.query.filter_by(
        photographer_id=photographer_id,
        date=booking_date,
    ).all()

    if not entries:
        return  # no schedule configured for this date — allow booking

    # Check for break/off overlap
    for entry in entries:
        if entry.type in ("break", "off"):
            if booking_start < entry.end_time and booking_end > entry.start_time:
                raise BookingError(
                    f"photographer is unavailable ({entry.type}) "
                    f"from {entry.start_time} to {entry.end_time}"
                )

    # Check that a working window covers the booking
    working_entries = [e for e in entries if e.type == "working"]
    if working_entries:
        covered = any(
            e.start_time <= booking_start and e.end_time >= booking_end
            for e in working_entries
        )
        if not covered:
            raise BookingError(
                "booking falls outside photographer's working hours"
            )


def create_booking(
    *,
    member_id: int,
    photographer_id: int,
    start_time: datetime,
    end_time: datetime,
    actor_id: int | None = None,
) -> Booking:
    if member_id is None:
        raise BookingError("member_id is required")
    if photographer_id is None:
        raise BookingError("photographer_id is required")
    _validate_times(start_time, end_time)

    if db.session.get(Member, member_id) is None:
        raise BookingError("member not found")
    photographer = db.session.get(User, photographer_id)
    if photographer is None:
        raise BookingError("photographer not found")
    if not photographer.has_role("photographer"):
        raise BookingError("user is not a photographer")

    # Validate against photographer schedule — must fall within a "working"
    # window and not overlap any "break" or "off" entry.
    _validate_schedule(photographer_id, start_time, end_time)

    conflict = _has_conflict(photographer_id, start_time, end_time)
    if conflict is not None:
        audit_service.log(
            actor_id=actor_id,
            action="booking_conflict_rejected",
            resource=f"photographer:{photographer_id}",
            metadata={
                "conflicting_booking_id": conflict.id,
                "requested_start": start_time.isoformat(),
                "requested_end": end_time.isoformat(),
            },
        )
        raise BookingError(
            f"time conflict with existing booking #{conflict.id}"
        )

    lock_expires = datetime.utcnow() + timedelta(minutes=LOCK_DURATION_MINUTES)
    booking = Booking(
        member_id=member_id,
        photographer_id=photographer_id,
        created_by=actor_id,
        start_time=start_time,
        end_time=end_time,
        status="locked",
        lock_expires_at=lock_expires,
    )
    db.session.add(booking)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="booking_created",
        resource=f"booking:{booking.id}",
        metadata={
            "member_id": member_id,
            "photographer_id": photographer_id,
            "lock_expires_at": lock_expires.isoformat(),
        },
    )
    return booking


def confirm_booking(
    booking: Booking,
    *,
    actor_id: int | None = None,
) -> Booking:
    if booking is None:
        raise BookingError("booking is required")
    if booking.status == "confirmed":
        raise BookingError("booking is already confirmed")
    if booking.status == "cancelled":
        raise BookingError("cannot confirm a cancelled booking")
    if booking.is_lock_expired():
        booking.status = "cancelled"
        db.session.commit()
        raise BookingError("lock has expired; booking was cancelled")

    # Re-check conflicts now (another booking may have been confirmed while
    # we held the lock).
    conflict = _has_conflict(
        booking.photographer_id,
        booking.start_time,
        booking.end_time,
        exclude_id=booking.id,
    )
    if conflict is not None:
        audit_service.log(
            actor_id=actor_id,
            action="booking_conflict_rejected",
            resource=f"booking:{booking.id}",
            metadata={"conflicting_booking_id": conflict.id},
        )
        raise BookingError(
            f"time conflict with booking #{conflict.id}; cannot confirm"
        )

    booking.status = "confirmed"
    booking.lock_expires_at = None
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="booking_confirmed",
        resource=f"booking:{booking.id}",
        metadata={},
    )
    return booking


def cancel_booking(
    booking: Booking,
    *,
    actor_id: int | None = None,
) -> Booking:
    if booking is None:
        raise BookingError("booking is required")
    if booking.status == "cancelled":
        raise BookingError("booking is already cancelled")
    booking.status = "cancelled"
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="booking_cancelled",
        resource=f"booking:{booking.id}",
        metadata={},
    )
    return booking


def get_by_id(booking_id: int) -> Booking | None:
    return db.session.get(Booking, booking_id)


def list_bookings(
    *,
    photographer_id: int | None = None,
    include_expired_locks: bool = False,
    actor_id: int | None = None,
) -> list[Booking]:
    query = Booking.query
    if photographer_id is not None:
        query = query.filter_by(photographer_id=photographer_id)

    # Actor-scoped filtering: admin and staff see all (operational visibility);
    # photographers and other roles see only their own created/assigned bookings.
    if actor_id is not None:
        from app.models.user import User

        actor = db.session.get(User, actor_id)
        if actor is not None and not actor.has_role("admin") and not actor.has_role("staff"):
            query = query.filter(
                or_(
                    Booking.created_by == actor_id,
                    Booking.photographer_id == actor_id,
                )
            )

    if not include_expired_locks:
        now = datetime.utcnow()
        # Exclude locked bookings whose lock has expired.
        query = query.filter(
            or_(
                Booking.status != "locked",
                and_(
                    Booking.status == "locked",
                    Booking.lock_expires_at > now,
                ),
            )
        )
    return query.order_by(Booking.start_time).all()


def get_availability(
    photographer_id: int,
    start: datetime,
    end: datetime,
) -> bool:
    """Return True if the photographer is available in the given window."""
    return _has_conflict(photographer_id, start, end) is None
