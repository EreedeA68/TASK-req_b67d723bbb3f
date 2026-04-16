"""Record-scope enforcement on points/redeem endpoint."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_redeem_denied_when_member_out_of_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Redemption blocked when staff's record-scope excludes the member."""
    from app.services import permission_service

    # Set up: admin creates an order for the member (so there's something to redeem against)
    _login(client, admin_user.username, "pw-admin-123")
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 100.0,
    })
    order_id = r.get_json()["id"]

    # Admin credits some points to the member
    from app.services import points_service
    points_service.earn_points(
        member_id=seeded_member.id, order_id=order_id,
        subtotal=100.0, actor_id=admin_user.id,
    )

    # Admin restricts staff to a different member id
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    # Staff tries to redeem for the scoped-out member
    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/points/redeem", json={
        "member_id": seeded_member.id,
        "order_id": order_id,
        "points": 5,
    })
    assert resp.status_code == 403


def test_redeem_denied_when_order_out_of_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Redemption blocked when staff's record-scope excludes the order."""
    from app.services import permission_service, points_service

    _login(client, admin_user.username, "pw-admin-123")
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 100.0,
    })
    order_id = r.get_json()["id"]
    points_service.earn_points(
        member_id=seeded_member.id, order_id=order_id,
        subtotal=100.0, actor_id=admin_user.id,
    )

    # Restrict order:pay to a different id
    permission_service.grant_permission(
        role_name="staff", resource="order", action="pay",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/points/redeem", json={
        "member_id": seeded_member.id,
        "order_id": order_id,
        "points": 5,
    })
    assert resp.status_code == 403


def test_redeem_allowed_when_in_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Redemption works when staff is within scope for both member and order."""
    from app.services import points_service

    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 100.0,
    })
    order_id = r.get_json()["id"]
    points_service.earn_points(
        member_id=seeded_member.id, order_id=order_id,
        subtotal=100.0, actor_id=staff_user.id,
    )

    resp = client.post("/api/points/redeem", json={
        "member_id": seeded_member.id,
        "order_id": order_id,
        "points": 5,
    })
    assert resp.status_code == 200
