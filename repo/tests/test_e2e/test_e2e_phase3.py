"""Phase 3 end-to-end flow tests."""
import os


def test_clockin_valid_and_invalid_flow(client, app):
    """E2E: valid clock-in, then invalid, verify audit."""
    import hashlib

    from app.db import db
    from app.models.audit import AuditLog
    from app.models.enrollment import Enrollment
    from app.services import auth_service

    user = auth_service.register("ci_user", "ci-pw-1", roles=["staff"])
    # Create enrollment for biometric verification
    db.session.add(Enrollment(
        user_id=user.id,
        reference_hash=hashlib.sha256(b"e2e-ref").hexdigest(),
        device_id="kiosk-e2e",
        active=True,
    ))
    db.session.commit()
    client.post("/api/auth/login", json={"username": "ci_user", "password": "ci-pw-1"})

    # Valid clock-in
    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.90,
        "brightness": 0.70,
        "face_count": 1,
        "device_id": "kiosk-e2e",
    })
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    # Invalid clock-in
    resp = client.post("/api/clock-in", json={
        "face_match_score": 0.50,
        "brightness": 0.20,
        "face_count": 3,
        "device_id": "kiosk-e2e",
    })
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

    actions = {a.action for a in AuditLog.query.all()}
    assert "clockin_success" in actions
    assert "clockin_failed" in actions


def test_risk_flag_block_clear_flow(client, app):
    """E2E: flag user -> check blocked -> admin clears -> check unblocked."""
    from app.models.audit import AuditLog
    from app.services import auth_service, risk_service

    user = auth_service.register("risk_user", "rp-1", roles=["staff"])
    admin = auth_service.register("risk_admin", "ra-1", roles=["admin"])

    # Flag the user
    risk_service.flag_user(user.id, "points_abuse")
    assert risk_service.has_active_flag(user.id, "points_abuse")

    # Admin clears
    client.post("/api/auth/login", json={"username": "risk_admin", "password": "ra-1"})
    resp = client.post(f"/api/risk/{user.id}/clear", json={})
    assert resp.status_code == 200
    assert resp.get_json()["cleared"] == 1
    assert not risk_service.has_active_flag(user.id)

    actions = {a.action for a in AuditLog.query.all()}
    assert "risk_flag_triggered" in actions
    assert "risk_flag_cleared" in actions


def test_export_and_verify_file(client, app, seeded_member):
    """E2E: create members -> export -> verify file exists with correct data."""
    from app.services import auth_service

    exp_user = auth_service.register("exp_user", "ep-1", roles=["staff"])
    client.post("/api/auth/login", json={"username": "exp_user", "password": "ep-1"})
    # Create an order so the actor has an interaction with seeded_member (scope requirement)
    client.post("/api/orders", json={"member_id": seeded_member.id, "subtotal": 5.0})

    resp = client.post("/api/exports", json={"type": "members"})
    assert resp.status_code == 201
    filepath = resp.get_json()["file_path"]
    assert os.path.exists(filepath)

    with open(filepath) as f:
        content = f.read()
    assert "M-TEST0001" in content
    assert "Jane Doe" in content


def test_snapshot_update_rollback_flow(client, app, seeded_member):
    """E2E: snapshot member -> change name -> rollback -> verify restored."""
    from app.db import db
    from app.models.audit import AuditLog
    from app.services import auth_service

    auth_service.register("ver_admin", "va-1", roles=["admin"])
    client.post("/api/auth/login", json={"username": "ver_admin", "password": "va-1"})

    # Snapshot
    resp = client.post(f"/api/versions/member/{seeded_member.id}/snapshot", json={})
    assert resp.status_code == 201

    # Modify
    seeded_member.name = "Modified Name"
    db.session.commit()
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.get_json()["name"] == "Modified Name"

    # Rollback
    resp = client.post(f"/api/versions/member/{seeded_member.id}/rollback", json={})
    assert resp.status_code == 200
    assert resp.get_json()["restored"]["name"] == "Jane Doe"

    # Verify via API
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.get_json()["name"] == "Jane Doe"

    actions = {a.action for a in AuditLog.query.all()}
    assert "version_snapshot" in actions
    assert "version_rollback" in actions
