"""Tests for admin enrollment API."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_create_enrollment_admin_only(app, client, staff_user, logged_in_staff):
    """Non-admin cannot create an enrollment."""
    resp = client.post(f"/api/enrollments/{staff_user.id}", json={
        "reference_data": "bio-sample-bytes",
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 403


def test_admin_creates_enrollment(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.post(f"/api/enrollments/{staff_user.id}", json={
        "reference_data": "bio-sample-bytes",
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["user_id"] == staff_user.id
    assert data["device_id"] == "kiosk-01"
    assert data["active"] is True


def test_create_enrollment_replaces_existing(app, client, admin_user, staff_user):
    """Creating a new enrollment deactivates the previous active one."""
    from app.models.enrollment import Enrollment

    _login(client, admin_user.username, "pw-admin-123")
    client.post(f"/api/enrollments/{staff_user.id}", json={
        "reference_data": "old-data", "device_id": "kiosk-01",
    })
    client.post(f"/api/enrollments/{staff_user.id}", json={
        "reference_data": "new-data", "device_id": "kiosk-02",
    })

    active = Enrollment.query.filter_by(user_id=staff_user.id, active=True).all()
    assert len(active) == 1
    assert active[0].device_id == "kiosk-02"


def test_deactivate_enrollment(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    client.post(f"/api/enrollments/{staff_user.id}", json={
        "reference_data": "bio-data", "device_id": "kiosk-01",
    })
    resp = client.delete(f"/api/enrollments/{staff_user.id}", json={})
    assert resp.status_code == 200
    assert resp.get_json()["deactivated"] == 1


def test_get_enrollment_not_found(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.get(f"/api/enrollments/{staff_user.id}")
    assert resp.status_code == 404


def test_enrollment_for_unknown_user(app, client, admin_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.post("/api/enrollments/99999", json={
        "reference_data": "bio-data",
    })
    assert resp.status_code == 404


def test_missing_reference_data_rejected(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.post(f"/api/enrollments/{staff_user.id}", json={})
    assert resp.status_code == 400
