"""Tests for server-side face-match verification against enrollment."""
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
    return enrollment


def test_server_match_with_correct_artifact(client, logged_in_staff, app):
    """Submitting the correct face_image_hash yields a successful match."""
    ref_data = b"test-ref"
    _enroll_user(logged_in_staff.id, ref_data)
    correct_hash = hashlib.sha256(ref_data).hexdigest()

    resp = client.post("/api/clock-in", json={
        "face_image_hash": correct_hash,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_server_match_with_wrong_artifact(client, logged_in_staff, app):
    """Submitting a mismatched face_image_hash is rejected."""
    _enroll_user(logged_in_staff.id, b"real-face")
    wrong_hash = hashlib.sha256(b"different-face").hexdigest()

    resp = client.post("/api/clock-in", json={
        "face_image_hash": wrong_hash,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "face_match" in data["reason"]


def test_server_match_overrides_client_score(client, logged_in_staff, app):
    """Even if client claims face_match_score=0.99, server computes from artifact."""
    _enroll_user(logged_in_staff.id, b"real-face")
    wrong_hash = hashlib.sha256(b"different-face").hexdigest()

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.99,
        "face_image_hash": wrong_hash,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    # Server ignores client score when artifact is provided
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_no_artifact_uses_client_fallback(client, logged_in_staff, app):
    """Without face_image_hash, client score is used (dev/test mode)."""
    _enroll_user(logged_in_staff.id)

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.90,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
