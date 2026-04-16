"""Record-scope and printable-receipt tests for /api/orders/<id>/receipt."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def _make_paid_order(client, member_id):
    r = client.post("/api/orders", json={
        "member_id": member_id, "subtotal": 50.0,
    })
    oid = r.get_json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={})
    return oid


def test_receipt_blocked_when_record_scope_excludes_order(
    app, client, staff_user, admin_user, seeded_member
):
    """Record-scope restricting order:view to a different id blocks receipt."""
    from app.services import permission_service

    _login(client, staff_user.username, "pw-staff-123")
    order_id = _make_paid_order(client, seeded_member.id)

    # Admin restricts staff to a different order id
    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="order", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/orders/{order_id}/receipt")
    assert resp.status_code == 403


def test_receipt_allowed_when_record_scope_matches(
    app, client, staff_user, admin_user, seeded_member
):
    """Matching record-scope allows receipt access."""
    from app.services import permission_service

    _login(client, staff_user.username, "pw-staff-123")
    order_id = _make_paid_order(client, seeded_member.id)

    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="order", action="view",
        scope_type="record", scope_value=str(order_id),
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/orders/{order_id}/receipt")
    assert resp.status_code == 200
    assert resp.get_json()["order_id"] == order_id


def test_printable_receipt_returns_plaintext(
    app, client, staff_user, seeded_member
):
    """/receipt/print returns text/plain payload with receipt body."""
    _login(client, staff_user.username, "pw-staff-123")
    order_id = _make_paid_order(client, seeded_member.id)

    resp = client.get(f"/api/orders/{order_id}/receipt/print")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    body = resp.data.decode()
    assert "WildLifeLens" in body
    assert f"Order #{order_id}" in body
    assert "TOTAL:" in body


def test_printable_receipt_respects_record_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Print endpoint honors record-scope just like JSON receipt."""
    from app.services import permission_service

    _login(client, staff_user.username, "pw-staff-123")
    order_id = _make_paid_order(client, seeded_member.id)

    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="order", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/orders/{order_id}/receipt/print")
    assert resp.status_code == 403
