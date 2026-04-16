"""KDS HTMX view tests — tickets partial, start/complete error paths."""


def _make_kds_ticket(client, seeded_member):
    """Create order via service layer and advance to in_prep, return (order_id, ticket_id).

    Uses services directly so the HTTP session (kitchen vs staff) does not matter.
    """
    from app.services import order_service
    from app.models.kds import KDSTicket

    order = order_service.create_order(
        member_id=seeded_member.id,
        subtotal=20.0,
        items=[{"name": "Burger", "category": "grill", "price": 20.0, "quantity": 1}],
    )
    order_service.pay(order)
    order_service.advance(order)  # → in_prep, creates KDS ticket

    ticket = KDSTicket.query.filter_by(order_id=order.id).first()
    return order.id, ticket.id


# ── KDS tickets partial ────────────────────────────────────────────────────

def test_kds_tickets_partial(client, logged_in_kitchen):
    resp = client.get("/kds/tickets")
    assert resp.status_code == 200
    assert b"<html" not in resp.data


def test_kds_tickets_partial_with_station_filter(client, logged_in_kitchen):
    resp = client.get("/kds/tickets?station=bar&status=pending")
    assert resp.status_code == 200


# ── Start ticket ───────────────────────────────────────────────────────────

def test_kds_start_not_found(client, logged_in_kitchen):
    resp = client.post("/kds/9999/start")
    assert resp.status_code == 404


def test_kds_start_success(app, client, logged_in_staff, seeded_member, logged_in_kitchen):
    _, ticket_id = _make_kds_ticket(client, seeded_member)
    resp = client.post(f"/kds/{ticket_id}/start")
    assert resp.status_code == 200


def test_kds_start_already_started_returns_400(
    app, client, logged_in_staff, seeded_member, logged_in_kitchen
):
    _, ticket_id = _make_kds_ticket(client, seeded_member)
    client.post(f"/kds/{ticket_id}/start")
    # Starting again should return 400
    resp = client.post(f"/kds/{ticket_id}/start")
    assert resp.status_code == 400


# ── Complete ticket ────────────────────────────────────────────────────────

def test_kds_complete_not_found(client, logged_in_kitchen):
    resp = client.post("/kds/9999/complete")
    assert resp.status_code == 404


def test_kds_complete_success(
    app, client, logged_in_staff, seeded_member, logged_in_kitchen
):
    _, ticket_id = _make_kds_ticket(client, seeded_member)
    client.post(f"/kds/{ticket_id}/start")
    resp = client.post(f"/kds/{ticket_id}/complete")
    assert resp.status_code == 200


def test_kds_complete_already_done_returns_400(
    app, client, logged_in_staff, seeded_member, logged_in_kitchen
):
    _, ticket_id = _make_kds_ticket(client, seeded_member)
    client.post(f"/kds/{ticket_id}/complete")  # pending → done
    resp = client.post(f"/kds/{ticket_id}/complete")  # already done → 400
    assert resp.status_code == 400
