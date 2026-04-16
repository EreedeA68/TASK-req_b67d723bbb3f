"""Stored-value balance/history masking tests."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_non_admin_cannot_see_raw_balance(
    app, client, staff_user, admin_user, seeded_member
):
    """Staff without explicit field grant sees masked balance."""
    from app.services import stored_value_service

    # Credit some balance
    stored_value_service.credit(
        member_id=seeded_member.id, amount=100.0,
        description="test", actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/stored-value/balance/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["balance"] == "****"  # masked


def test_admin_sees_raw_balance(
    app, client, admin_user, seeded_member
):
    """Admin sees the raw numeric balance."""
    from app.services import stored_value_service

    stored_value_service.credit(
        member_id=seeded_member.id, amount=100.0,
        description="test", actor_id=admin_user.id,
    )

    _login(client, admin_user.username, "pw-admin-123")
    resp = client.get(f"/api/stored-value/balance/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["balance"] == 100.0


def test_non_admin_history_amounts_masked(
    app, client, staff_user, admin_user, seeded_member
):
    """Staff sees masked amounts in history."""
    from app.services import stored_value_service

    stored_value_service.credit(
        member_id=seeded_member.id, amount=50.0,
        description="test", actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/stored-value/history/{seeded_member.id}")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert len(results) >= 1
    for entry in results:
        assert entry["amount"] == "****"


def test_staff_with_field_grant_sees_raw_balance(
    app, client, staff_user, admin_user, seeded_member
):
    """Explicit field-scope grant unlocks raw balance for staff."""
    from app.services import permission_service, stored_value_service

    stored_value_service.credit(
        member_id=seeded_member.id, amount=75.0,
        description="test", actor_id=admin_user.id,
    )
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="field", scope_value="stored_value_balance",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/stored-value/balance/{seeded_member.id}")
    assert resp.status_code == 200
    assert resp.get_json()["balance"] == 75.0
