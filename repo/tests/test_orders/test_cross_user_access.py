"""Cross-user object-level authorization tests for orders.

Validates that non-operational-role users cannot access orders created by
other users, while operational roles (admin/staff/kitchen) can.
"""


def _create_order(client, member_id):
    resp = client.post("/api/orders", json={
        "member_id": member_id, "subtotal": 50.0,
    })
    assert resp.status_code == 201
    return resp.get_json()["id"]


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_non_owner_member_denied(
    app, client, staff_user, seeded_member
):
    """A member-role user cannot view an order created by staff."""
    from app.services import auth_service

    # Staff creates an order
    _login(client, staff_user.username, "pw-staff-123")
    order_id = _create_order(client, seeded_member.id)

    # Register a member-role user and login
    member_user = auth_service.register("member1", "pw-member-123", roles=["member"])
    _login(client, member_user.username, "pw-member-123")

    # Member cannot view staff's order
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 403


def test_non_owner_photographer_denied(
    app, client, staff_user, photographer_user, seeded_member
):
    """A photographer cannot view orders they didn't create."""
    _login(client, staff_user.username, "pw-staff-123")
    order_id = _create_order(client, seeded_member.id)

    _login(client, photographer_user.username, "pw-photo-123")
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 403


def test_admin_can_access_any_order(
    app, client, staff_user, admin_user, seeded_member
):
    """Admin can access orders created by anyone."""
    _login(client, staff_user.username, "pw-staff-123")
    order_id = _create_order(client, seeded_member.id)

    _login(client, admin_user.username, "pw-admin-123")
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200


def test_kitchen_can_access_any_order(
    app, client, staff_user, kitchen_user, seeded_member
):
    """Kitchen staff can access orders for workflow continuity."""
    _login(client, staff_user.username, "pw-staff-123")
    order_id = _create_order(client, seeded_member.id)

    _login(client, kitchen_user.username, "pw-kitchen-123")
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200


def test_other_staff_can_access_order(
    app, client, staff_user, seeded_member
):
    """Another staff member can access orders (operational role)."""
    from app.services import auth_service

    _login(client, staff_user.username, "pw-staff-123")
    order_id = _create_order(client, seeded_member.id)

    staff2 = auth_service.register("staff2", "pw-staff2-123", roles=["staff"])
    _login(client, staff2.username, "pw-staff2-123")
    resp = client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200


def test_non_owner_cannot_pay_order(
    app, client, staff_user, seeded_member
):
    """A member-role user cannot pay an order they didn't create."""
    from app.services import auth_service

    _login(client, staff_user.username, "pw-staff-123")
    order_id = _create_order(client, seeded_member.id)

    member_user = auth_service.register("member2", "pw-member2-123", roles=["member"])
    _login(client, member_user.username, "pw-member2-123")

    resp = client.post(f"/api/orders/{order_id}/pay", json={})
    assert resp.status_code == 403
