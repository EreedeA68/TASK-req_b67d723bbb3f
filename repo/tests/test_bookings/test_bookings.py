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


# --- booking_service service-level error paths ---

def test_check_access_none_booking_raises(app, staff_user):
    import pytest
    from app.services.booking_service import BookingAccessDenied, check_access
    with pytest.raises(BookingAccessDenied):
        check_access(None, staff_user.id)


def test_check_access_none_actor_raises(app, photographer_user, seeded_member, future_booking_times):
    import pytest
    from app.services.booking_service import BookingAccessDenied, check_access, create_booking
    start, end = future_booking_times
    booking = create_booking(
        member_id=seeded_member.id,
        photographer_id=photographer_user.id,
        start_time=start,
        end_time=end,
    )
    with pytest.raises(BookingAccessDenied):
        check_access(booking, None)


def test_check_access_unknown_actor_raises(app, photographer_user, seeded_member, future_booking_times):
    import pytest
    from app.services.booking_service import BookingAccessDenied, check_access, create_booking
    start, end = future_booking_times
    booking = create_booking(
        member_id=seeded_member.id,
        photographer_id=photographer_user.id,
        start_time=start,
        end_time=end,
    )
    with pytest.raises(BookingAccessDenied):
        check_access(booking, 99999)


def test_create_booking_none_member_id_raises(app, photographer_user, future_booking_times):
    import pytest
    from app.services.booking_service import BookingError, create_booking
    start, end = future_booking_times
    with pytest.raises(BookingError, match="member_id is required"):
        create_booking(member_id=None, photographer_id=photographer_user.id, start_time=start, end_time=end)


def test_create_booking_none_photographer_id_raises(app, seeded_member, future_booking_times):
    import pytest
    from app.services.booking_service import BookingError, create_booking
    start, end = future_booking_times
    with pytest.raises(BookingError, match="photographer_id is required"):
        create_booking(member_id=seeded_member.id, photographer_id=None, start_time=start, end_time=end)


def test_create_booking_member_not_found_raises(app, photographer_user, future_booking_times):
    import pytest
    from app.services.booking_service import BookingError, create_booking
    start, end = future_booking_times
    with pytest.raises(BookingError, match="member not found"):
        create_booking(member_id=99999, photographer_id=photographer_user.id, start_time=start, end_time=end)


def test_create_booking_photographer_not_found_raises(app, seeded_member, future_booking_times):
    import pytest
    from app.services.booking_service import BookingError, create_booking
    start, end = future_booking_times
    with pytest.raises(BookingError, match="photographer not found"):
        create_booking(member_id=seeded_member.id, photographer_id=99999, start_time=start, end_time=end)


def test_create_booking_non_photographer_user_raises(app, seeded_member, staff_user, future_booking_times):
    import pytest
    from app.services.booking_service import BookingError, create_booking
    start, end = future_booking_times
    with pytest.raises(BookingError, match="not a photographer"):
        create_booking(
            member_id=seeded_member.id, photographer_id=staff_user.id,
            start_time=start, end_time=end,
        )


def test_confirm_none_booking_raises(app):
    import pytest
    from app.services.booking_service import BookingError, confirm_booking
    with pytest.raises(BookingError, match="required"):
        confirm_booking(None)


def test_cancel_none_booking_raises(app):
    import pytest
    from app.services.booking_service import BookingError, cancel_booking
    with pytest.raises(BookingError, match="required"):
        cancel_booking(None)


def test_list_bookings_photographer_filter(app, photographer_user, seeded_member, future_booking_times):
    from app.services.booking_service import create_booking, list_bookings
    start, end = future_booking_times
    create_booking(
        member_id=seeded_member.id, photographer_id=photographer_user.id,
        start_time=start, end_time=end,
    )
    results = list_bookings(photographer_id=photographer_user.id, include_expired_locks=True)
    assert all(b.photographer_id == photographer_user.id for b in results)


def test_list_bookings_non_staff_actor_scoped(app, photographer_user, seeded_member, future_booking_times):
    from app.services.booking_service import create_booking, list_bookings
    start, end = future_booking_times
    create_booking(
        member_id=seeded_member.id, photographer_id=photographer_user.id,
        start_time=start, end_time=end,
    )
    results = list_bookings(actor_id=photographer_user.id, include_expired_locks=True)
    assert len(results) >= 1


def test_get_availability(app, photographer_user, future_booking_times):
    from app.services.booking_service import get_availability
    start, end = future_booking_times
    available = get_availability(photographer_user.id, start, end)
    assert available is True
