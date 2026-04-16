"""Tests that canonical replay detection cannot be bypassed by varying client claims."""
import hashlib

from app.db import db
from app.models.enrollment import Enrollment


def _enroll_user(user_id, reference_data=b"test-ref", device_id="kiosk-01"):
    enrollment = Enrollment(
        user_id=user_id,
        reference_hash=hashlib.sha256(reference_data).hexdigest(),
        device_id=device_id,
        active=True,
    )
    db.session.add(enrollment)
    db.session.commit()
    return enrollment


def test_same_artifact_varied_claim_blocked(client, logged_in_staff, app):
    """Replay of same artifact with varied client face_match_score is blocked."""
    ref_data = b"test-ref"
    _enroll_user(logged_in_staff.id, ref_data)
    correct_hash = hashlib.sha256(ref_data).hexdigest()

    # First submission with client score 0.90
    resp1 = client.post("/api/clock-in", json={
        "face_image_hash": correct_hash,
        "face_match_score": 0.90,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp1.status_code == 200

    # Replay with different client-claimed score — must still be blocked
    # because canonical hash is derived from the artifact hash, not client score.
    resp2 = client.post("/api/clock-in", json={
        "face_image_hash": correct_hash,
        "face_match_score": 0.95,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp2.status_code == 400
    assert "duplicate" in resp2.get_json()["error"]


def test_device_mismatch_rejected(client, logged_in_staff, app):
    """Clock-in fails when device_id does not match enrollment's device."""
    _enroll_user(logged_in_staff.id, device_id="kiosk-01")

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.90,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-02",  # mismatch
    })
    assert resp.status_code == 400
    assert "device_not_enrolled" in resp.get_json()["reason"]


def test_device_match_allowed(client, logged_in_staff, app):
    """Clock-in with matching device_id succeeds."""
    _enroll_user(logged_in_staff.id, device_id="kiosk-01")

    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.90,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
