"""Tests that HTML/HTMX view routes enforce record-level ABAC parity with the API."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_order_detail_view_blocked_by_record_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """GET /orders/{id} must honor record-scope (not just the API)."""
    from app.services import permission_service

    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order_id = r.get_json()["id"]

    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="order", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/orders/{order_id}")
    assert resp.status_code == 403


def test_order_pay_view_blocked_by_record_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """POST /orders/{id}/pay must honor record-scope."""
    from app.services import permission_service

    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order_id = r.get_json()["id"]

    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="order", action="pay",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post(f"/orders/{order_id}/pay", data={})
    assert resp.status_code == 403


def test_order_advance_view_blocked_by_record_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """POST /orders/{id}/advance must honor record-scope."""
    from app.services import permission_service

    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order_id = r.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="order", action="advance",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post(f"/orders/{order_id}/advance", data={})
    assert resp.status_code == 403


def test_booking_confirm_view_blocked_by_record_scope(
    app, client, staff_user, admin_user, photographer_user, seeded_member
):
    """POST /bookings/{id}/confirm must honor record-scope."""
    from datetime import date, datetime, time, timedelta

    from app.db import db
    from app.models.schedule import PhotographerSchedule
    from app.services import permission_service

    tomorrow = date.today() + timedelta(days=1)
    db.session.add(PhotographerSchedule(
        photographer_id=photographer_user.id,
        date=tomorrow,
        start_time=time(9, 0),
        end_time=time(17, 0),
        type="working",
    ))
    db.session.commit()

    _login(client, staff_user.username, "pw-staff-123")
    start = datetime.combine(tomorrow, time(10, 0))
    end = datetime.combine(tomorrow, time(11, 0))
    r = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    booking_id = r.get_json()["id"]

    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="booking", action="confirm",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post(f"/bookings/{booking_id}/confirm", data={})
    assert resp.status_code == 403


def test_booking_cancel_view_blocked_by_record_scope(
    app, client, staff_user, admin_user, photographer_user, seeded_member
):
    """POST /bookings/{id}/cancel must honor record-scope."""
    from datetime import date, datetime, time, timedelta

    from app.db import db
    from app.models.schedule import PhotographerSchedule
    from app.services import permission_service

    tomorrow = date.today() + timedelta(days=1)
    db.session.add(PhotographerSchedule(
        photographer_id=photographer_user.id,
        date=tomorrow,
        start_time=time(9, 0),
        end_time=time(17, 0),
        type="working",
    ))
    db.session.commit()

    _login(client, staff_user.username, "pw-staff-123")
    start = datetime.combine(tomorrow, time(10, 0))
    end = datetime.combine(tomorrow, time(11, 0))
    r = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    booking_id = r.get_json()["id"]

    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="booking", action="cancel",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post(f"/bookings/{booking_id}/cancel", data={})
    assert resp.status_code == 403


def test_order_create_picker_filters_by_record_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """GET /orders/create should only list members in the staff record-scope."""
    from app.services import member_service, permission_service

    # Create a second member only staff will see
    member2 = member_service.create_member(
        name="Picker Target", phone_number="5559998888",
        member_id="M-PICK0001", actor_id=admin_user.id,
    )

    # Restrict staff to member2 only
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value=str(member2.id),
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get("/orders/create")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Picker Target" in html
    # Seeded member is out of scope — must not appear in the picker
    assert seeded_member.member_id not in html
