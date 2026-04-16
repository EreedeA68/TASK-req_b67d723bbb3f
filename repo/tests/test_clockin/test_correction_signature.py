"""Correction-generated punches use the tamper-evident signature scheme."""
from datetime import datetime, timedelta


def test_approved_correction_punch_has_proper_signature(
    app, client, logged_in_staff, admin_user
):
    """Signature on correction-created TimePunch is SHA-256 hex + canonical_hash set."""
    from app.models.timepunch import TimePunch

    # Staff submits correction
    resp = client.post("/api/corrections", json={
        "punch_type": "clock_in",
        "requested_time": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
        "reason": "forgot to punch in",
    })
    correction_id = resp.get_json()["id"]

    # Admin approves
    client.post("/api/auth/logout", json={})
    client.post("/api/auth/login", json={
        "username": admin_user.username, "password": "pw-admin-123",
    })
    resp = client.post(f"/api/corrections/{correction_id}/approve", json={})
    assert resp.status_code == 200

    # Check the created punch
    punch = (TimePunch.query
             .filter(TimePunch.reason.like(f"approved_correction:{correction_id}"))
             .first())
    assert punch is not None
    # Signature is 64-char SHA-256 hex, NOT the old predictable form
    assert punch.signature is not None
    assert len(punch.signature) == 64
    assert all(ch in "0123456789abcdef" for ch in punch.signature)
    assert not punch.signature.startswith("correction-")
    # canonical_hash is also populated
    assert punch.canonical_hash is not None
    assert len(punch.canonical_hash) == 64


def test_correction_signatures_unique_per_approval(
    app, client, logged_in_staff, admin_user
):
    """Two different corrections produce two different signatures."""
    from app.models.timepunch import TimePunch

    # Submit two corrections
    for i in range(2):
        client.post("/api/corrections", json={
            "punch_type": "clock_in",
            "requested_time": (datetime.utcnow() - timedelta(hours=i+1)).isoformat(),
            "reason": f"correction #{i}",
        })

    # Admin approves both
    client.post("/api/auth/logout", json={})
    client.post("/api/auth/login", json={
        "username": admin_user.username, "password": "pw-admin-123",
    })
    from app.models.punch_correction import PunchCorrection
    for c in PunchCorrection.query.filter_by(status="pending").all():
        client.post(f"/api/corrections/{c.id}/approve", json={})

    punches = (TimePunch.query
               .filter(TimePunch.reason.like("approved_correction:%"))
               .all())
    assert len(punches) == 2
    sigs = {p.signature for p in punches}
    assert len(sigs) == 2  # signatures are unique
