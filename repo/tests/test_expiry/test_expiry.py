"""Order expiry tests — unpaid and paid timeouts."""
from datetime import datetime, timedelta


def test_unpaid_order_not_expired_within_window(
    app, client, logged_in_staff, seeded_member
):
    """Fresh unpaid order should not be expired."""
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    oid = r.get_json()["id"]
    resp = client.get(f"/api/orders/{oid}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "created"


def test_unpaid_order_expired_after_30_minutes(
    app, client, logged_in_staff, seeded_member
):
    from app.db import db
    from app.models.audit import AuditLog
    from app.models.order import Order

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    oid = r.get_json()["id"]
    # Backdate the order
    order = db.session.get(Order, oid)
    order.created_at = datetime.utcnow() - timedelta(minutes=31)
    db.session.commit()
    # Fetch triggers expiry
    resp = client.get(f"/api/orders/{oid}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cancelled"
    # Audit
    assert AuditLog.query.filter_by(action="order_expired").count() == 1
    md = AuditLog.query.filter_by(action="order_expired").first().get_metadata()
    assert md["reason"] == "unpaid_timeout"


def test_ready_order_moves_to_pickup_after_4_hours(
    app, client, logged_in_staff, seeded_member
):
    """Ready orders transition to ready_for_pickup after 4 hours."""
    from app.db import db
    from app.models.order import Order, OrderEvent

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    oid = r.get_json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={})
    client.post(f"/api/orders/{oid}/advance", json={})  # in_prep
    client.post(f"/api/orders/{oid}/advance", json={})  # ready
    # Backdate the "ready" event so it looks like it was ready 5 hours ago
    ready_event = OrderEvent.query.filter_by(order_id=oid, status="ready").first()
    ready_event.timestamp = datetime.utcnow() - timedelta(hours=5)
    db.session.commit()
    resp = client.get(f"/api/orders/{oid}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ready_for_pickup"


def test_in_prep_order_not_expired(
    app, client, logged_in_staff, seeded_member
):
    """Orders beyond 'paid' (i.e., 'in_prep'+) should never auto-expire."""
    from app.db import db
    from app.models.order import Order

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    oid = r.get_json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={})
    client.post(f"/api/orders/{oid}/advance", json={})  # -> in_prep
    order = db.session.get(Order, oid)
    order.created_at = datetime.utcnow() - timedelta(hours=10)
    db.session.commit()
    resp = client.get(f"/api/orders/{oid}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "in_prep"


def test_expired_order_cannot_be_paid(
    app, client, logged_in_staff, seeded_member
):
    """Once expired, paying should fail (cancelled is a final state)."""
    from app.db import db
    from app.models.order import Order

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    oid = r.get_json()["id"]
    order = db.session.get(Order, oid)
    order.created_at = datetime.utcnow() - timedelta(minutes=31)
    db.session.commit()
    # Fetch triggers expiry
    client.get(f"/api/orders/{oid}")
    resp = client.post(f"/api/orders/{oid}/pay", json={})
    assert resp.status_code == 400
    assert "final" in resp.get_json()["error"].lower()
