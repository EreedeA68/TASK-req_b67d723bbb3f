"""Tests that CLOCKIN_FACE_THRESHOLD is configurable via the Config layer."""
import hashlib

from app.db import db
from app.models.enrollment import Enrollment


def _enroll_user(user_id, reference_data=b"ref"):
    enrollment = Enrollment(
        user_id=user_id,
        reference_hash=hashlib.sha256(reference_data).hexdigest(),
        device_id="kiosk-01",
        active=True,
    )
    db.session.add(enrollment)
    db.session.commit()


def test_default_threshold_is_0_85(app):
    """Config default matches prompt spec."""
    assert app.config["CLOCKIN_FACE_THRESHOLD"] == 0.85


def test_higher_threshold_rejects_moderate_score(app, client, logged_in_staff):
    """Raising threshold causes a 0.88 score to fail."""
    _enroll_user(logged_in_staff.id)
    app.config["CLOCKIN_FACE_THRESHOLD"] = 0.95

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.88,
        "brightness": 0.80,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 400
    assert "face_match_score" in resp.get_json()["reason"]

    # Restore default so subsequent tests aren't affected
    app.config["CLOCKIN_FACE_THRESHOLD"] = 0.85


def test_lower_threshold_accepts_low_score(app, client, logged_in_staff):
    """Lowering threshold accepts a 0.70 score."""
    _enroll_user(logged_in_staff.id)
    app.config["CLOCKIN_FACE_THRESHOLD"] = 0.50

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.70,
        "brightness": 0.80,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200

    app.config["CLOCKIN_FACE_THRESHOLD"] = 0.85
