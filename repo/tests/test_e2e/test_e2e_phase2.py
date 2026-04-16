"""Phase 2 end-to-end flow tests."""
from datetime import datetime, timedelta


def test_schedule_booking_confirm_flow(
    client, app, seeded_member, photographer_user
):
    """E2E: schedule photographer -> create booking -> confirm booking."""
    from app.models.audit import AuditLog
    from app.services import auth_service

    # Staff user
    auth_service.register("e2e_s2", "e2e-pw-2", roles=["staff"])
    client.post("/api/auth/login", json={
        "username": "e2e_s2", "password": "e2e-pw-2",
    })

    # 1. Create schedule
    resp = client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-06-01",
        "start_time": "09:00",
        "end_time": "17:00",
    })
    assert resp.status_code == 201

    # 2. Create booking
    start = datetime(2026, 6, 1, 10, 0)
    end = datetime(2026, 6, 1, 11, 0)
    resp = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 201
    bid = resp.get_json()["id"]
    assert resp.get_json()["status"] == "locked"

    # 3. Confirm booking
    resp = client.post(f"/api/bookings/{bid}/confirm", json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "confirmed"

    # Audit trail
    actions = {a.action for a in AuditLog.query.all()}
    assert "schedule_created" in actions
    assert "booking_created" in actions
    assert "booking_confirmed" in actions


def test_order_to_kds_flow(client, app, seeded_member):
    """E2E: create order -> pay -> advance to in_prep -> KDS ticket appears."""
    from app.models.audit import AuditLog
    from app.services import auth_service, kds_service, order_service

    auth_service.register("e2e_kds", "e2e-pw-3", roles=["staff"])
    client.post("/api/auth/login", json={
        "username": "e2e_kds", "password": "e2e-pw-3",
    })

    # 1. Create + pay + advance
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 50.0,
    })
    oid = r.get_json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={})
    client.post(f"/api/orders/{oid}/advance", json={})

    # 2. Generate KDS tickets
    order = order_service.get_by_id(oid, check_expiry=False)
    assert order.status == "in_prep"
    tickets = kds_service.generate_tickets(
        order, stations=["grill", "bar"], priority=1, eta_minutes=10
    )
    assert len(tickets) == 2

    # 3. Kitchen user works on tickets
    auth_service.register("e2e_kitchen", "e2e-pw-4", roles=["kitchen"])
    client.post("/api/auth/logout", json={})
    client.post("/api/auth/login", json={
        "username": "e2e_kitchen", "password": "e2e-pw-4",
    })
    for t in tickets:
        resp = client.post(f"/api/kds/{t.id}/start", json={})
        assert resp.status_code == 200
        resp = client.post(f"/api/kds/{t.id}/complete", json={})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "done"

    # Audit
    actions = {a.action for a in AuditLog.query.all()}
    assert "kds_ticket_created" in actions


def test_booking_conflict_flow(
    client, app, seeded_member, photographer_user
):
    """E2E: two overlapping bookings — first succeeds, second rejected."""
    from app.services import auth_service

    auth_service.register("e2e_conflict", "e2e-pw-5", roles=["staff"])
    client.post("/api/auth/login", json={
        "username": "e2e_conflict", "password": "e2e-pw-5",
    })
    start = datetime(2026, 7, 1, 10, 0)
    end = datetime(2026, 7, 1, 12, 0)
    r1 = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert r1.status_code == 201
    r2 = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": (start + timedelta(hours=1)).isoformat(),
        "end_time": (end + timedelta(hours=1)).isoformat(),
    })
    assert r2.status_code == 400
    assert "conflict" in r2.get_json()["error"].lower()


def test_order_expiry_flow(client, app, seeded_member):
    """E2E: create order -> let it expire -> verify cancelled -> cannot pay."""
    from app.db import db
    from app.models.order import Order
    from app.services import auth_service

    auth_service.register("e2e_exp", "e2e-pw-6", roles=["staff"])
    client.post("/api/auth/login", json={
        "username": "e2e_exp", "password": "e2e-pw-6",
    })
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    oid = r.get_json()["id"]
    # Backdate
    order = db.session.get(Order, oid)
    order.created_at = datetime.utcnow() - timedelta(minutes=31)
    db.session.commit()
    # Fetch triggers expiry
    resp = client.get(f"/api/orders/{oid}")
    assert resp.get_json()["status"] == "cancelled"
    # Cannot pay
    resp = client.post(f"/api/orders/{oid}/pay", json={})
    assert resp.status_code == 400
