"""Explicit field-scope grant unmasks phone_number for non-admin."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_staff_phone_masked_by_default(client, logged_in_staff, seeded_member):
    """Without a field grant, staff sees masked phone."""
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
    phone = resp.get_json()["phone_number"]
    assert phone.startswith("****")
    assert "5551234567" not in phone


def test_staff_phone_unmasked_with_explicit_grant(
    app, client, staff_user, admin_user, seeded_member
):
    """Admin grants staff field-level access to phone_number → staff sees plaintext."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="field", scope_value="phone_number",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    # Phone is now visible in plaintext
    assert data["phone_number"] == "5551234567"
    # stored_value_balance is still masked (no grant for it)
    assert data["stored_value_balance"] == "****"


def test_staff_multiple_field_grants(
    app, client, staff_user, admin_user, seeded_member
):
    """Multiple field grants unmask multiple fields."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="field", scope_value="phone_number",
        actor_id=admin_user.id,
    )
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="field", scope_value="stored_value_balance",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/members/{seeded_member.id}")
    data = resp.get_json()
    assert data["phone_number"] == "5551234567"
    # stored_value_balance is plaintext "0" (seeded default)
    assert data["stored_value_balance"] == "0"


def test_admin_sees_phone_unmasked_without_grant(
    app, client, admin_user, seeded_member
):
    """Admin always sees raw phone."""
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.get(f"/api/members/{seeded_member.id}")
    data = resp.get_json()
    assert data["phone_number"] == "5551234567"
