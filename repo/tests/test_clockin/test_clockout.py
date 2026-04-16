"""Clock-out and punch correction tests."""
from datetime import datetime, timedelta


# ---- Clock-out API tests ----

def _clockout(client, **overrides):
    payload = {"device_id": "kiosk-01"}
    payload.update(overrides)
    return client.post("/api/clock-out", json=payload)


def test_clock_out_success(client, logged_in_staff, app):
    from app.models.audit import AuditLog
    from app.models.timepunch import TimePunch

    resp = _clockout(client)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["punch_type"] == "clock_out"
    assert data["signature"] is not None
    assert data["reason"] is None
    # DB
    punch = TimePunch.query.first()
    assert punch is not None
    assert punch.punch_type == "clock_out"
    # Audit
    assert AuditLog.query.filter_by(action="clockout_success").count() == 1


def test_clock_out_rate_limited(client, logged_in_staff, app):
    from app.models.audit import AuditLog

    # Use up the rate limit — vary device_id to avoid anti-replay block
    for i in range(3):
        _clockout(client, device_id=f"kiosk-{i:02d}")
    # 4th should be rate-limited
    resp = _clockout(client, device_id="kiosk-03")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "rate_limit" in data["reason"]
    rate_audits = AuditLog.query.filter_by(action="clockout_failed").all()
    assert any("rate_limit" in (a.get_metadata().get("reason") or "") for a in rate_audits)


def test_clock_out_requires_auth(client):
    resp = _clockout(client)
    assert resp.status_code == 401


def test_clock_out_requires_device_id(client, logged_in_staff):
    resp = _clockout(client, device_id="")
    assert resp.status_code == 400


# ---- Correction API tests ----

def _submit_correction(client, **overrides):
    payload = {
        "punch_type": "clock_in",
        "requested_time": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
        "reason": "Forgot to clock in this morning",
    }
    payload.update(overrides)
    return client.post("/api/corrections", json=payload)


def test_correction_submit(client, logged_in_staff, app):
    from app.models.audit import AuditLog
    from app.models.punch_correction import PunchCorrection

    resp = _submit_correction(client)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "pending"
    assert data["requested_type"] == "clock_in"
    assert data["reason"] == "Forgot to clock in this morning"
    # DB
    assert PunchCorrection.query.count() == 1
    # Audit
    assert AuditLog.query.filter_by(action="correction_submitted").count() == 1


def test_correction_submit_requires_reason(client, logged_in_staff):
    resp = _submit_correction(client, reason="")
    assert resp.status_code == 400


def test_correction_submit_invalid_punch_type(client, logged_in_staff):
    resp = _submit_correction(client, punch_type="invalid")
    assert resp.status_code == 400


def test_correction_list_own(client, logged_in_staff, app):
    """Staff can only see their own corrections."""
    _submit_correction(client)
    resp = client.get("/api/corrections")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1


def test_correction_admin_approve(client, logged_in_staff, admin_user, app):
    from app.models.audit import AuditLog

    # Staff submits correction
    resp = _submit_correction(client)
    correction_id = resp.get_json()["id"]

    # Log in as admin
    client.post("/api/auth/login", json={
        "username": admin_user.username,
        "password": "pw-admin-123",
    })

    # Admin approves
    resp = client.post(f"/api/corrections/{correction_id}/approve", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "approved"
    assert data["reviewed_by"] == admin_user.id
    assert data["reviewed_at"] is not None
    # Audit
    assert AuditLog.query.filter_by(action="correction_approved").count() == 1


def test_correction_admin_reject(client, logged_in_staff, admin_user, app):
    from app.models.audit import AuditLog

    # Staff submits correction
    resp = _submit_correction(client)
    correction_id = resp.get_json()["id"]

    # Log in as admin
    client.post("/api/auth/login", json={
        "username": admin_user.username,
        "password": "pw-admin-123",
    })

    # Admin rejects
    resp = client.post(f"/api/corrections/{correction_id}/reject", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "rejected"
    assert data["reviewed_by"] == admin_user.id
    # Audit
    assert AuditLog.query.filter_by(action="correction_rejected").count() == 1


def test_correction_creates_punch_on_approve(client, logged_in_staff, admin_user, app):
    """Approving a correction creates a corrected TimePunch."""
    from app.models.timepunch import TimePunch

    # Staff submits correction
    resp = _submit_correction(client, punch_type="clock_out")
    correction_id = resp.get_json()["id"]

    # Log in as admin
    client.post("/api/auth/login", json={
        "username": admin_user.username,
        "password": "pw-admin-123",
    })

    initial_count = TimePunch.query.count()

    # Admin approves
    resp = client.post(f"/api/corrections/{correction_id}/approve", json={})
    assert resp.status_code == 200

    # A new TimePunch should have been created
    assert TimePunch.query.count() == initial_count + 1
    new_punch = TimePunch.query.order_by(TimePunch.id.desc()).first()
    assert new_punch.punch_type == "clock_out"
    assert new_punch.success is True
    assert "approved_correction" in new_punch.reason


def test_correction_staff_cannot_approve(client, logged_in_staff, app):
    """Non-admin users cannot approve corrections."""
    resp = _submit_correction(client)
    correction_id = resp.get_json()["id"]

    # Staff tries to approve (should fail with 403)
    resp = client.post(f"/api/corrections/{correction_id}/approve", json={})
    assert resp.status_code == 403


def test_correction_cannot_approve_twice(client, logged_in_staff, admin_user, app):
    """Cannot approve a correction that is already approved."""
    resp = _submit_correction(client)
    correction_id = resp.get_json()["id"]

    # Log in as admin
    client.post("/api/auth/login", json={
        "username": admin_user.username,
        "password": "pw-admin-123",
    })

    # First approve
    resp = client.post(f"/api/corrections/{correction_id}/approve", json={})
    assert resp.status_code == 200

    # Second approve should fail
    resp = client.post(f"/api/corrections/{correction_id}/approve", json={})
    assert resp.status_code == 400


# ---- UI tests ----

def test_clockin_page_shows_clock_out(client, logged_in_staff):
    """The kiosk page should show both clock-in and clock-out forms."""
    resp = client.get("/clock-in")
    assert resp.status_code == 200
    assert b"Clock Out" in resp.data
    assert b"clockout-result" in resp.data


def test_clock_out_ui_success(client, logged_in_staff):
    resp = client.post("/clock-in/clock-out", data={
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
    assert b"clockout-success" in resp.data


def test_clock_out_ui_missing_device(client, logged_in_staff):
    resp = client.post("/clock-in/clock-out", data={
        "device_id": "",
    })
    assert resp.status_code == 400
    assert b"clockout-error" in resp.data
