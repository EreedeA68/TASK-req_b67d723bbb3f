"""Tests that search respects order:view permission + object-level access."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_photographer_search_does_not_leak_orders(
    app, client, staff_user, photographer_user, seeded_member
):
    """Photographer has search:perform but not order:view — must see no orders."""
    # Staff creates an order
    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 25.0,
    })
    assert resp.status_code == 201

    # Switch to photographer and search
    _login(client, photographer_user.username, "pw-photo-123")
    resp = client.get("/api/search?q=created")
    assert resp.status_code == 200
    data = resp.get_json()
    # Photographer must not see any orders
    assert data["orders"] == []


def test_staff_search_returns_orders(
    app, client, staff_user, seeded_member
):
    """Staff has order:view — search returns matching orders."""
    _login(client, staff_user.username, "pw-staff-123")
    client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 25.0,
    })
    resp = client.get("/api/search?q=created")
    assert resp.status_code == 200
    assert len(resp.get_json()["orders"]) >= 1


def test_admin_search_returns_all_orders(
    app, client, admin_user, staff_user, seeded_member
):
    """Admin sees all orders regardless of creator."""
    _login(client, staff_user.username, "pw-staff-123")
    client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 30.0,
    })
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.get("/api/search?q=created")
    assert resp.status_code == 200
    assert len(resp.get_json()["orders"]) >= 1
