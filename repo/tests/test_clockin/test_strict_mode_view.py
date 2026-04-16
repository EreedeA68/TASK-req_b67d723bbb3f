"""Tests that the HTMX kiosk view works under default strict mode."""
import hashlib

from app.db import db
from app.models.enrollment import Enrollment


def _enroll_user(user_id, reference_data=b"my-face-bytes"):
    enrollment = Enrollment(
        user_id=user_id,
        reference_hash=hashlib.sha256(reference_data).hexdigest(),
        device_id="kiosk-01",
        active=True,
    )
    db.session.add(enrollment)
    db.session.commit()


def test_strict_mode_view_accepts_artifact(app, client, logged_in_staff):
    """With CLOCKIN_STRICT=True, the kiosk view succeeds when the form
    includes a matching face_image_hash."""
    ref = b"my-face-bytes"
    _enroll_user(logged_in_staff.id, ref)
    app.config["CLOCKIN_STRICT"] = True

    correct_hash = hashlib.sha256(ref).hexdigest()
    resp = client.post("/clock-in/submit", data={
        "face_image_hash": correct_hash,
        "brightness": "0.80",
        "face_count": "1",
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
    assert b"clockin-success" in resp.data

    app.config["CLOCKIN_STRICT"] = False


def test_strict_mode_view_rejects_without_artifact(app, client, logged_in_staff):
    """With CLOCKIN_STRICT=True, submitting without face_image_hash is
    rejected and the UI partial surfaces the reason."""
    _enroll_user(logged_in_staff.id)
    app.config["CLOCKIN_STRICT"] = True

    resp = client.post("/clock-in/submit", data={
        "face_match_score": "0.99",
        "brightness": "0.80",
        "face_count": "1",
        "device_id": "kiosk-01",
    })
    # Partial returns 200 OK status but body reports failure
    assert resp.status_code == 200
    assert b"artifact_required" in resp.data

    app.config["CLOCKIN_STRICT"] = False


def test_lax_mode_view_accepts_claim(app, client, logged_in_staff):
    """Default test config (non-strict) still accepts client-claim submissions."""
    _enroll_user(logged_in_staff.id)
    assert app.config.get("CLOCKIN_STRICT") is False

    resp = client.post("/clock-in/submit", data={
        "face_match_score": "0.90",
        "brightness": "0.80",
        "face_count": "1",
        "device_id": "kiosk-01",
    })
    assert resp.status_code == 200
    assert b"clockin-success" in resp.data


def test_kiosk_page_has_capture_button(app, client, logged_in_staff):
    """The kiosk form exposes the capture helper so operators can produce
    a face_image_hash without typing one manually."""
    resp = client.get("/clock-in")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "face-image-hash" in html
    assert "btn-capture" in html
    assert 'name="face_image_hash"' in html
