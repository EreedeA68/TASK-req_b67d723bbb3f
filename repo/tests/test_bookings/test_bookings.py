"""Booking tests — API, conflict detection, lock expiry, audit."""
from datetime import datetime, timedelta


def _mk_booking(client, member_id, photographer_id, start, end):
    return client.post("/api/bookings", json={
        "member_id": member_id,
        "photographer_id": photographer_id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })


def test_create_booking_requires_auth(
    client, seeded_member, photographer_user, future_booking_times
):
    start, end = future_booking_times
    resp = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    assert resp.status_code == 401


def test_create_booking_success(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times, app
):
    from app.models.audit import AuditLog
    from app.models.booking import Booking

    start, end = future_booking_times
    resp = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "locked"
    assert data["lock_expires_at"] is not None
    # DB
    assert Booking.query.count() == 1
    # Audit
    assert AuditLog.query.filter_by(action="booking_created").count() == 1


def test_booking_conflict_rejected(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times, app
):
    from app.models.audit import AuditLog

    start, end = future_booking_times
    _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    # Overlapping second booking
    resp = _mk_booking(
        client, seeded_member.id, photographer_user.id,
        start + timedelta(minutes=30), end + timedelta(minutes=30),
    )
    assert resp.status_code == 400
    assert "conflict" in resp.get_json()["error"].lower()
    assert AuditLog.query.filter_by(action="booking_conflict_rejected").count() == 1


def test_booking_no_conflict_different_photographer(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times, app
):
    from app.services import auth_service

    photo2 = auth_service.register("photo2", "pw-photo2", roles=["photographer"])
    start, end = future_booking_times
    _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    resp = _mk_booking(client, seeded_member.id, photo2.id, start, end)
    assert resp.status_code == 201


def test_confirm_booking(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times, app
):
    from app.models.audit import AuditLog

    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    resp = client.post(f"/api/bookings/{bid}/confirm", json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "confirmed"
    assert AuditLog.query.filter_by(action="booking_confirmed").count() == 1


def test_cancel_booking(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times
):
    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    resp = client.post(f"/api/bookings/{bid}/cancel", json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cancelled"


def test_confirm_already_cancelled_rejected(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times
):
    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    client.post(f"/api/bookings/{bid}/cancel", json={})
    resp = client.post(f"/api/bookings/{bid}/confirm", json={})
    assert resp.status_code == 400


def test_lock_expiry_allows_new_booking(
    app, client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times
):
    """An expired lock should not block a new booking."""
    from app.models.booking import Booking

    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    # Manually expire the lock
    booking = Booking.query.get(bid)
    booking.lock_expires_at = datetime.utcnow() - timedelta(minutes=1)
    from app.db import db
    db.session.commit()
    # New booking at same time should succeed because the old lock is expired.
    resp = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    assert resp.status_code == 201


def test_confirm_expired_lock_rejected(
    app, client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times
):
    """Confirming an expired lock should fail."""
    from app.models.booking import Booking
    from app.db import db

    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    booking = Booking.query.get(bid)
    booking.lock_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    resp = client.post(f"/api/bookings/{bid}/confirm", json={})
    assert resp.status_code == 400
    assert "expired" in resp.get_json()["error"].lower()


def test_list_bookings(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times
):
    start, end = future_booking_times
    _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    resp = client.get("/api/bookings")
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) == 1


def test_booking_start_before_end_rejected(
    client, logged_in_staff, seeded_member, photographer_user
):
    now = datetime.utcnow() + timedelta(days=1)
    resp = _mk_booking(
        client, seeded_member.id, photographer_user.id,
        now, now - timedelta(hours=1),
    )
    assert resp.status_code == 400


def test_booking_not_found(client, logged_in_staff):
    resp = client.post("/api/bookings/99999/confirm", json={})
    assert resp.status_code == 404


def test_cancel_not_found(client, logged_in_staff):
    resp = client.post("/api/bookings/99999/cancel", json={})
    assert resp.status_code == 404


def test_cancel_already_cancelled_returns_400(
    client, logged_in_staff, seeded_member, photographer_user, future_booking_times
):
    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    client.post(f"/api/bookings/{bid}/cancel", json={})
    resp = client.post(f"/api/bookings/{bid}/cancel", json={})
    assert resp.status_code == 400


def test_confirm_not_found(client, logged_in_staff):
    resp = client.post("/api/bookings/99999/confirm", json={})
    assert resp.status_code == 404


def test_confirm_already_confirmed_returns_400(
    client, logged_in_staff, seeded_member, photographer_user, future_booking_times
):
    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    client.post(f"/api/bookings/{bid}/confirm", json={})
    resp = client.post(f"/api/bookings/{bid}/confirm", json={})
    assert resp.status_code == 400


def test_booking_ui_page(client, logged_in_staff, seeded_member):
    resp = client.get("/bookings")
    assert resp.status_code == 200
    assert b"Bookings" in resp.data


def test_booking_confirm_partial(
    client, logged_in_staff, seeded_member, photographer_user,
    future_booking_times
):
    start, end = future_booking_times
    r = _mk_booking(client, seeded_member.id, photographer_user.id, start, end)
    bid = r.get_json()["id"]
    resp = client.post(f"/bookings/{bid}/confirm")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"confirmed" in resp.data
