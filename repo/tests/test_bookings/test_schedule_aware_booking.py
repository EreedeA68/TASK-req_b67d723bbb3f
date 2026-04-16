"""Tests for schedule-aware booking validation."""
from datetime import date, datetime, time, timedelta

from app.db import db
from app.models.schedule import PhotographerSchedule


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def _add_schedule(photographer_id, sched_date, start, end, stype="working"):
    entry = PhotographerSchedule(
        photographer_id=photographer_id,
        date=sched_date,
        start_time=start,
        end_time=end,
        type=stype,
    )
    db.session.add(entry)
    db.session.commit()


def test_booking_rejected_during_break(
    app, client, staff_user, photographer_user, seeded_member
):
    """Cannot book a photographer during a break."""
    _login(client, staff_user.username, "pw-staff-123")

    tomorrow = date.today() + timedelta(days=1)
    _add_schedule(photographer_user.id, tomorrow, time(9, 0), time(17, 0), "working")
    _add_schedule(photographer_user.id, tomorrow, time(12, 0), time(13, 0), "break")

    start = datetime.combine(tomorrow, time(12, 0))
    end = datetime.combine(tomorrow, time(12, 30))

    resp = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 400
    assert "break" in resp.get_json()["error"].lower()


def test_booking_rejected_on_off_day(
    app, client, staff_user, photographer_user, seeded_member
):
    """Cannot book a photographer on their day off."""
    _login(client, staff_user.username, "pw-staff-123")

    tomorrow = date.today() + timedelta(days=1)
    _add_schedule(photographer_user.id, tomorrow, time(0, 0), time(23, 59), "off")

    start = datetime.combine(tomorrow, time(10, 0))
    end = datetime.combine(tomorrow, time(11, 0))

    resp = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 400
    assert "off" in resp.get_json()["error"].lower()


def test_booking_rejected_outside_working_hours(
    app, client, staff_user, photographer_user, seeded_member
):
    """Cannot book outside working hours when schedule exists."""
    _login(client, staff_user.username, "pw-staff-123")

    tomorrow = date.today() + timedelta(days=1)
    _add_schedule(photographer_user.id, tomorrow, time(9, 0), time(17, 0), "working")

    start = datetime.combine(tomorrow, time(18, 0))
    end = datetime.combine(tomorrow, time(19, 0))

    resp = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 400
    assert "working hours" in resp.get_json()["error"].lower()


def test_booking_allowed_within_working_hours(
    app, client, staff_user, photographer_user, seeded_member
):
    """Booking within working hours (no break overlap) succeeds."""
    _login(client, staff_user.username, "pw-staff-123")

    tomorrow = date.today() + timedelta(days=1)
    _add_schedule(photographer_user.id, tomorrow, time(9, 0), time(17, 0), "working")

    start = datetime.combine(tomorrow, time(10, 0))
    end = datetime.combine(tomorrow, time(11, 0))

    resp = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 201


def test_booking_allowed_when_no_schedule(
    app, client, staff_user, photographer_user, seeded_member
):
    """Booking is allowed when no schedule is configured for the date."""
    _login(client, staff_user.username, "pw-staff-123")

    tomorrow = date.today() + timedelta(days=1)
    start = datetime.combine(tomorrow, time(10, 0))
    end = datetime.combine(tomorrow, time(11, 0))

    resp = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 201
