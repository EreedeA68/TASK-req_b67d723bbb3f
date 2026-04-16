"""Tests for explicit minutes-late KDS alert message."""
from datetime import datetime, timedelta

from app.db import db


def test_minutes_late_computed(app, logged_in_staff, client, seeded_member):
    from app.services import kds_service, order_service

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order_id = r.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/advance", json={})

    order = order_service.get_by_id(order_id, check_expiry=False)
    tickets = kds_service.generate_tickets(order, eta_minutes=5)
    ticket = tickets[0]

    # Backdate to simulate 12-min late
    ticket.created_at = datetime.utcnow() - timedelta(minutes=17)
    db.session.commit()

    assert ticket.is_late()
    assert ticket.minutes_late() >= 11  # at least 12 with tolerance for slow tests
    alert = ticket.late_alert()
    assert alert is not None
    assert "late by" in alert
    assert "min" in alert


def test_on_time_has_no_late_alert(app, logged_in_staff, client, seeded_member):
    from app.services import kds_service, order_service

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order_id = r.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/advance", json={})
    order = order_service.get_by_id(order_id, check_expiry=False)

    tickets = kds_service.generate_tickets(order, eta_minutes=60)
    ticket = tickets[0]

    assert ticket.is_late() is False
    assert ticket.minutes_late() == 0
    assert ticket.late_alert() is None


def test_kds_row_renders_minutes_late(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    """KDS template shows 'late by N min' rather than generic LATE."""
    from app.services import kds_service, order_service

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order_id = r.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/advance", json={})
    order = order_service.get_by_id(order_id, check_expiry=False)

    tickets = kds_service.generate_tickets(order, eta_minutes=2)
    ticket = tickets[0]
    ticket.created_at = datetime.utcnow() - timedelta(minutes=15)
    db.session.commit()

    client.post("/api/auth/logout", json={})
    client.post("/api/auth/login", json={
        "username": kitchen_user.username, "password": "pw-kitchen-123",
    })
    resp = client.get("/kds/tickets")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "late by" in html
    assert "min" in html
