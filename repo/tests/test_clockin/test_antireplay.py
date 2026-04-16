"""Anti-replay robustness tests for clock-in.

Validates that identical logical payloads are blocked even when the nonce
and timestamp differ between submissions.
"""
import hashlib

from app.db import db
from app.models.enrollment import Enrollment


def _enroll_user(user_id):
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


def test_replay_identical_payload_blocked(client, logged_in_staff, app):
    """Two identical logical payloads should be rejected as replay."""
    _enroll_user(logged_in_staff.id)

    resp1 = _clockin(client)
    assert resp1.status_code == 200
    assert resp1.get_json()["success"] is True

    # Second submission with identical payload — should be blocked
    resp2 = _clockin(client)
    assert resp2.status_code == 400
    assert "duplicate" in resp2.get_json()["error"]


def test_different_payload_not_blocked(client, logged_in_staff, app):
    """Different biometric values produce different canonical hashes and are allowed."""
    _enroll_user(logged_in_staff.id)

    resp1 = _clockin(client, face_match_score=0.90)
    assert resp1.status_code == 200

    resp2 = _clockin(client, face_match_score=0.91)
    assert resp2.status_code == 200


def test_canonical_hash_stored(client, logged_in_staff, app):
    """Successful punches store a canonical_hash for future replay detection."""
    from app.models.timepunch import TimePunch

    _enroll_user(logged_in_staff.id)
    resp = _clockin(client)
    assert resp.status_code == 200

    punch = TimePunch.query.first()
    assert punch is not None
    assert punch.canonical_hash is not None
    assert len(punch.canonical_hash) == 64  # SHA-256 hex


def test_replay_with_different_device_rejected(client, logged_in_staff, app):
    """Device policy: device_id must match enrollment — alternate devices rejected."""
    _enroll_user(logged_in_staff.id)  # enrollment has device_id="kiosk-01"

    resp1 = _clockin(client, device_id="kiosk-01")
    assert resp1.status_code == 200

    # Different device — now rejected by device policy (not anti-replay)
    resp2 = _clockin(client, device_id="kiosk-02")
    assert resp2.status_code == 400
    assert "device_not_enrolled" in resp2.get_json()["reason"]
