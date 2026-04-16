"""KDS category-based routing and completion write-back tests.

Validates that order items with different categories route to the correct
KDS stations, and that completing all tickets writes back to the order
event pipeline and auto-advances the order.
"""
from app.db import db


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_items_route_to_correct_stations(
    app, logged_in_staff, client, seeded_member
):
    """Order items with different categories should route to mapped stations."""
    from app.models.kds import KDSTicket
    from app.services import kds_service

    # Create order with items spanning multiple categories
    resp = client.post("/api/orders", json={
        "member_id": seeded_member.id,
        "subtotal": 45.0,
        "items": [
            {"name": "Cola", "category": "drink", "quantity": 1, "unit_price": 5.0},
            {"name": "Steak", "category": "grill", "quantity": 1, "unit_price": 25.0},
            {"name": "Cake Slice", "category": "dessert", "quantity": 1, "unit_price": 15.0},
        ],
    })
    assert resp.status_code == 201
    order_id = resp.get_json()["id"]

    # Pay then advance to in_prep (triggers KDS generation)
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/advance", json={})

    tickets = KDSTicket.query.filter_by(order_id=order_id).all()
    stations = {t.station for t in tickets}

    # drink -> bar, grill -> grill, dessert -> pastry
    assert "bar" in stations
    assert "grill" in stations
    assert "pastry" in stations


def test_map_station_known_categories(app):
    """map_station should return correct station for known categories."""
    from app.services.kds_service import map_station

    assert map_station("drink") == "bar"
    assert map_station("beverage") == "bar"
    assert map_station("dessert") == "pastry"
    assert map_station("cake") == "pastry"
    assert map_station("salad") == "cold"
    assert map_station("soup") == "hot"
    assert map_station("grill") == "grill"


def test_map_station_unknown_defaults(app):
    """Unknown categories should fall back to default station."""
    from app.services.kds_service import map_station

    assert map_station("unknown") == "grill"
    assert map_station("") == "grill"
    assert map_station(None) == "grill"


def test_completion_writeback_creates_order_event(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    """Completing a KDS ticket should write an OrderEvent back."""
    from app.models.order import OrderEvent
    from app.services import kds_service, order_service

    resp = client.post("/api/orders", json={
        "member_id": seeded_member.id,
        "subtotal": 20.0,
    })
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/advance", json={})

    order = order_service.get_by_id(order_id, check_expiry=False)
    tickets = kds_service.generate_tickets(order)
    ticket = tickets[0]

    _login(client, kitchen_user.username, "pw-kitchen-123")
    client.post(f"/api/kds/{ticket.id}/start", json={})
    client.post(f"/api/kds/{ticket.id}/complete", json={})

    # Check that a kds_completed event was written
    events = OrderEvent.query.filter(
        OrderEvent.order_id == order_id,
        OrderEvent.status.like("kds_completed:%"),
    ).all()
    assert len(events) >= 1


def test_all_tickets_done_auto_advances_order(
    app, kitchen_user, logged_in_staff, client, seeded_member
):
    """When all KDS tickets for an order are done, order auto-advances to ready."""
    from app.services import order_service

    resp = client.post("/api/orders", json={
        "member_id": seeded_member.id,
        "subtotal": 20.0,
        "items": [
            {"name": "Steak", "category": "grill", "quantity": 1, "unit_price": 20.0},
        ],
    })
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/advance", json={})

    from app.models.kds import KDSTicket
    tickets = KDSTicket.query.filter_by(order_id=order_id).all()
    assert len(tickets) >= 1

    _login(client, kitchen_user.username, "pw-kitchen-123")
    for ticket in tickets:
        client.post(f"/api/kds/{ticket.id}/complete", json={})

    # Order should have auto-advanced to "ready"
    order = order_service.get_by_id(order_id, check_expiry=False)
    assert order.status == "ready"


def test_allergy_flag_set_from_items(
    app, logged_in_staff, client, seeded_member
):
    """If any order item has an allergy_note, the KDS ticket gets allergy_flag."""
    from app.models.kds import KDSTicket

    resp = client.post("/api/orders", json={
        "member_id": seeded_member.id,
        "subtotal": 25.0,
        "items": [
            {
                "name": "Steak", "category": "grill",
                "quantity": 1, "unit_price": 25.0,
                "allergy_note": "nut allergy",
            },
        ],
    })
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/advance", json={})

    tickets = KDSTicket.query.filter_by(order_id=order_id).all()
    assert any(t.allergy_flag for t in tickets)
