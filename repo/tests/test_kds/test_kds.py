"""KDS tests — ticket creation, lifecycle, audit, UI."""


def _make_in_prep_order(client, seeded_member):
    """Create an order and advance it to in_prep, return order_id."""
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    oid = r.get_json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={})
    client.post(f"/api/orders/{oid}/advance", json={})
    return oid


def _login_kitchen(client, kitchen_user):
    """Switch session to kitchen user."""
    client.post("/api/auth/logout", json={})
    client.post("/api/auth/login", json={
        "username": kitchen_user.username, "password": "pw-kitchen-123",
    })


def test_kds_requires_auth(client):
    resp = client.get("/api/kds")
    assert resp.status_code == 401


def test_generate_kds_ticket(app, logged_in_staff, client, seeded_member):
    from app.models.audit import AuditLog
    from app.models.kds import KDSTicket

    # Advancing to in_prep auto-generates KDS tickets
    oid = _make_in_prep_order(client, seeded_member)
    tickets = KDSTicket.query.filter_by(order_id=oid).all()
    assert len(tickets) >= 1
    assert tickets[0].station == "grill"
    assert tickets[0].status == "pending"
    # Audit
    assert AuditLog.query.filter_by(action="kds_ticket_created").count() >= 1


def test_generate_kds_ticket_wrong_status_rejected(
    app, logged_in_staff, client, seeded_member
):
    from app.services import kds_service, order_service
    from app.services.kds_service import KDSError
    import pytest

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 20.0,
    })
    order = order_service.get_by_id(r.get_json()["id"], check_expiry=False)
    with pytest.raises(KDSError):
        kds_service.generate_tickets(order)


def test_kds_start_and_complete(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    from app.services import kds_service, order_service

    oid = _make_in_prep_order(client, seeded_member)
    order = order_service.get_by_id(oid, check_expiry=False)
    tickets = kds_service.generate_tickets(order)
    tid = tickets[0].id
    _login_kitchen(client, kitchen_user)
    # Start
    resp = client.post(f"/api/kds/{tid}/start", json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "in_progress"
    # Complete
    resp = client.post(f"/api/kds/{tid}/complete", json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "done"


def test_kds_start_non_pending_rejected(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    from app.services import kds_service, order_service

    oid = _make_in_prep_order(client, seeded_member)
    order = order_service.get_by_id(oid, check_expiry=False)
    tickets = kds_service.generate_tickets(order)
    tid = tickets[0].id
    _login_kitchen(client, kitchen_user)
    client.post(f"/api/kds/{tid}/start", json={})
    resp = client.post(f"/api/kds/{tid}/start", json={})
    assert resp.status_code == 400


def test_kds_list(app, kitchen_user, logged_in_staff, client, seeded_member):
    # Auto-generates tickets on in_prep transition
    _make_in_prep_order(client, seeded_member)
    _login_kitchen(client, kitchen_user)
    resp = client.get("/api/kds")
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) >= 1


def test_kds_list_filter_by_station(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    # Auto-generates tickets on in_prep transition (default station: grill)
    _make_in_prep_order(client, seeded_member)
    _login_kitchen(client, kitchen_user)
    resp = client.get("/api/kds?station=grill")
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) == 1


def test_kds_ticket_not_found(client, logged_in_kitchen):
    resp = client.post("/api/kds/99999/start", json={})
    assert resp.status_code == 404


def test_kds_is_late_flag(app, logged_in_staff, client, seeded_member):
    from app.services import kds_service, order_service
    from app.db import db
    from datetime import datetime, timedelta

    oid = _make_in_prep_order(client, seeded_member)
    order = order_service.get_by_id(oid, check_expiry=False)
    tickets = kds_service.generate_tickets(order, eta_minutes=1)
    ticket = tickets[0]
    ticket.created_at = datetime.utcnow() - timedelta(minutes=10)
    db.session.commit()
    assert ticket.is_late()


def test_kds_ui_page(client, logged_in_kitchen):
    resp = client.get("/kds")
    assert resp.status_code == 200
    assert b"Kitchen Display" in resp.data


def test_kds_ui_tickets_partial(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    from app.services import kds_service, order_service

    oid = _make_in_prep_order(client, seeded_member)
    order = order_service.get_by_id(oid, check_expiry=False)
    kds_service.generate_tickets(order)
    _login_kitchen(client, kitchen_user)
    resp = client.get("/kds/tickets")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"kds-row" in resp.data


def test_kds_start_partial(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    from app.services import kds_service, order_service

    oid = _make_in_prep_order(client, seeded_member)
    order = order_service.get_by_id(oid, check_expiry=False)
    tickets = kds_service.generate_tickets(order)
    tid = tickets[0].id
    _login_kitchen(client, kitchen_user)
    resp = client.post(f"/kds/{tid}/start")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"in_progress" in resp.data
