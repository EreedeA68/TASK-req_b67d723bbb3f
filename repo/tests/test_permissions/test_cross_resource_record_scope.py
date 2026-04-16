"""Tests for record-scope ABAC uniformly applied across resources."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_record_scope_on_order_view(
    app, client, staff_user, admin_user, seeded_member
):
    """Record-scope configured for order:view blocks non-matching records."""
    from app.services import permission_service

    # Staff creates an order
    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 30.0,
    })
    order_id = resp.get_json()["id"]

    # Admin grants staff record-level access to only a different order id
    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="order", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    # Staff now denied on the order they actually created
    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 403


def test_record_scope_on_booking_confirm(
    app, client, staff_user, admin_user, photographer_user, seeded_member
):
    """Record-scope blocks non-admin from confirming a booking outside scope."""
    from datetime import date, datetime, time, timedelta

    from app.db import db
    from app.models.schedule import PhotographerSchedule
    from app.services import permission_service

    # Add a schedule so booking creation succeeds
    tomorrow = date.today() + timedelta(days=1)
    db.session.add(PhotographerSchedule(
        photographer_id=photographer_user.id,
        date=tomorrow,
        start_time=time(9, 0),
        end_time=time(17, 0),
        type="working",
    ))
    db.session.commit()

    # Staff creates a booking
    _login(client, staff_user.username, "pw-staff-123")
    start = datetime.combine(tomorrow, time(10, 0))
    end = datetime.combine(tomorrow, time(11, 0))
    resp = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 201
    booking_id = resp.get_json()["id"]

    # Admin adds record-scope allowing only id=99999
    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="booking", action="confirm",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    # Staff cannot confirm their own booking
    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post(f"/api/bookings/{booking_id}/confirm", json={})
    assert resp.status_code == 403


def test_admin_bypasses_record_scope(
    app, client, admin_user, staff_user, seeded_member
):
    """Admin ignores record-scope constraints even when records exist."""
    from app.services import permission_service

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order_id = resp.get_json()["id"]

    permission_service.grant_permission(
        role_name="staff", resource="order", action="view",
        scope_type="record", scope_value="99999",
    )

    _login(client, admin_user.username, "pw-admin-123")
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200
