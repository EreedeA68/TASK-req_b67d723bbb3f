"""Clock-in validation tests."""
import hashlib
import pytest

from app.db import db
from app.models.enrollment import Enrollment


@pytest.fixture(autouse=True)
def _ensure_enrollment(app, request):
    """Auto-create enrollment for any test that has a logged-in staff user."""
    yield
    # Enrollment is created on demand in individual tests or via enrolled_staff fixture.


def _enroll_user(user_id):
    """Create an enrollment record for a user so clock-in biometric checks pass."""
    enrollment = Enrollment(
        user_id=user_id,
        reference_hash=hashlib.sha256(b"test-ref").hexdigest(),
        device_id="kiosk-01",
        active=True,
    )
    db.session.add(enrollment)
    db.session.commit()


def _clockin(client, **overrides):
    payload = {
        "face_match_score": 0.90,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    }
    payload.update(overrides)
    return client.post("/api/clock-in", json=payload)


def test_clockin_requires_auth(client):
    resp = _clockin(client)
    assert resp.status_code == 401


def test_clockin_success(client, logged_in_staff, app):
    from app.models.audit import AuditLog
    from app.models.timepunch import TimePunch

    _enroll_user(logged_in_staff.id)
    resp = _clockin(client)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["signature"] is not None
    assert data["reason"] is None
    # DB
    assert TimePunch.query.count() == 1
    # Audit
    assert AuditLog.query.filter_by(action="clockin_success").count() == 1


def test_clockin_low_face_match_rejected(client, logged_in_staff, app):
    from app.models.audit import AuditLog

    _enroll_user(logged_in_staff.id)
    resp = _clockin(client, face_match_score=0.50)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "face_match_score" in data["reason"]
    assert AuditLog.query.filter_by(action="clockin_failed").count() == 1


def test_clockin_low_brightness_rejected(client, logged_in_staff):
    _enroll_user(logged_in_staff.id)
    resp = _clockin(client, brightness=0.10)
    assert resp.status_code == 400
    assert "brightness" in resp.get_json()["reason"]


def test_clockin_wrong_face_count_rejected(client, logged_in_staff):
    _enroll_user(logged_in_staff.id)
    resp = _clockin(client, face_count=2)
    assert resp.status_code == 400
    assert "face_count" in resp.get_json()["reason"]


def test_clockin_multiple_failures_combined(client, logged_in_staff):
    _enroll_user(logged_in_staff.id)
    resp = _clockin(client, face_match_score=0.50, brightness=0.10, face_count=0)
    data = resp.get_json()
    assert data["success"] is False
    assert "face_match_score" in data["reason"]
    assert "brightness" in data["reason"]
    assert "face_count" in data["reason"]


def test_clockin_rate_limit(client, logged_in_staff, app):
    """After 3 attempts in 5 minutes, subsequent attempts are rate-limited."""
    from app.models.audit import AuditLog

    _enroll_user(logged_in_staff.id)
    # Use slightly different biometrics each time to avoid anti-replay block
    for i in range(3):
        _clockin(client, face_match_score=0.90 + i * 0.01)
    # 4th should be rate-limited
    resp = _clockin(client, face_match_score=0.93)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "rate_limit" in data["reason"]
    rate_audits = AuditLog.query.filter_by(action="clockin_failed").all()
    assert any("rate_limit" in (a.get_metadata().get("reason") or "") for a in rate_audits)


def test_clockin_signature_present(client, logged_in_staff):
    _enroll_user(logged_in_staff.id)
    resp = _clockin(client)
    sig = resp.get_json()["signature"]
    assert sig is not None
    assert len(sig) == 64  # SHA-256 hex


def test_clockin_ui_page(client, logged_in_staff):
    resp = client.get("/clock-in")
    assert resp.status_code == 200
    assert b"Clock-In" in resp.data


def test_clockin_ui_success_partial(client, logged_in_staff):
    _enroll_user(logged_in_staff.id)
    resp = client.post("/clock-in/submit", data={
        "face_match_score": "0.90",
        "brightness": "0.70",
        "face_count": "1",
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"clockin-success" in resp.data


def test_clockin_ui_failure_partial(client, logged_in_staff):
    _enroll_user(logged_in_staff.id)
    resp = client.post("/clock-in/submit", data={
        "face_match_score": "0.50",
        "brightness": "0.70",
        "face_count": "1",
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200  # HTMX partial still 200, but content says failure
    assert b"<html" not in resp.data
    assert b"clockin-failure" in resp.data


def test_clockin_ui_invalid_input_returns_400(client, logged_in_staff):
    resp = client.post("/clock-in/submit", data={
        "face_match_score": "not-a-number",
        "brightness": "0.70",
        "face_count": "1",
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 400


def test_correction_invalid_datetime_returns_400(client, logged_in_staff):
    resp = client.post("/clock-in/correction", data={
        "punch_type": "clock_in",
        "requested_time": "not-a-date",
        "reason": "forgot",
    })
    assert resp.status_code == 400


def test_correction_submit_success(client, logged_in_staff):
    from datetime import datetime, timedelta
    future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    resp = client.post("/clock-in/correction", data={
        "punch_type": "clock_in",
        "requested_time": future_time,
        "reason": "forgot to punch in",
    })
    assert resp.status_code == 200


def test_correction_invalid_punch_type_returns_400(client, logged_in_staff):
    from datetime import datetime, timedelta
    future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    resp = client.post("/clock-in/correction", data={
        "punch_type": "invalid_type",
        "requested_time": future_time,
        "reason": "test",
    })
    assert resp.status_code == 400
