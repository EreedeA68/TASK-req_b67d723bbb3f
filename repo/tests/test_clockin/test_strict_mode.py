"""Tests for strict clock-in mode (enrollment + artifact required)."""
import hashlib

from app.db import db
from app.models.enrollment import Enrollment


def _enroll_user(user_id, reference_data=b"test-ref"):
    enrollment = Enrollment(
        user_id=user_id,
        reference_hash=hashlib.sha256(reference_data).hexdigest(),
        device_id="kiosk-01",
        active=True,
    )
    db.session.add(enrollment)
    db.session.commit()


def test_strict_mode_rejects_claim_only(app, client, logged_in_staff):
    """With CLOCKIN_STRICT=True, clock-in without face_image_hash is rejected."""
    _enroll_user(logged_in_staff.id)
    app.config["CLOCKIN_STRICT"] = True

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.99,
        "brightness": 0.80,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 400
    assert "artifact_required" in resp.get_json()["reason"]

    app.config["CLOCKIN_STRICT"] = False  # restore for subsequent tests


def test_strict_mode_accepts_with_artifact(app, client, logged_in_staff):
    """Strict mode accepts clock-in when face_image_hash is provided."""
    ref = b"my-face-bytes"
    _enroll_user(logged_in_staff.id, ref)
    app.config["CLOCKIN_STRICT"] = True

    correct_hash = hashlib.sha256(ref).hexdigest()
    resp = client.post("/api/clock-in", json={
        "face_image_hash": correct_hash,
        "brightness": 0.80,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    app.config["CLOCKIN_STRICT"] = False


def test_lax_mode_accepts_claim(app, client, logged_in_staff):
    """Default test config is lax — client claim allowed."""
    _enroll_user(logged_in_staff.id)
    assert app.config.get("CLOCKIN_STRICT") is False  # TestConfig default

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.90,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
