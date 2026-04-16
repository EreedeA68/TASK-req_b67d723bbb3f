"""Integration tests: ABAC field/record scope enforced at API endpoints."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_member_api_applies_field_restriction(
    app, client, staff_user, admin_user, seeded_member
):
    """When field-scope limits staff to phone_number, other sensitive fields are masked."""
    from app.services import permission_service

    # Admin grants staff field-level access to phone_number only
    _login(client, admin_user.username, "pw-admin-123")
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="field", scope_value="phone_number",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    # points_balance should be masked
    assert data["points_balance"] == "***"
    # stored_value_balance should be masked
    assert data["stored_value_balance"] == "****"


def test_member_api_record_scope_blocks_access(
    app, client, staff_user, admin_user, seeded_member
):
    """When record-scope is configured, staff can only see allowed records."""
    from app.services import permission_service

    # Grant staff record-level access to a different member ID (not seeded_member)
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 403


def test_member_api_record_scope_allows_matching(
    app, client, staff_user, admin_user, seeded_member
):
    """Record-scope with matching ID allows access."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value=str(seeded_member.id),
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
    assert resp.get_json()["name"] == seeded_member.name


def test_member_search_filters_by_record_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Search results should be filtered by record-level scope."""
    from app.services import permission_service, member_service

    # Create a second member
    member2 = member_service.create_member(
        name="Bob Smith", phone_number="5559999999",
        member_id="M-TEST0002", actor_id=admin_user.id,
    )

    # Grant staff record access to member2 only
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value=str(member2.id),
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")

    # Search for a term that matches both members
    resp = client.get("/api/members/search?q=M-TEST")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    ids = [r["id"] for r in results]
    # Only member2 should be visible
    assert member2.id in ids
    assert seeded_member.id not in ids


def test_admin_bypasses_all_scope(
    app, client, admin_user, seeded_member
):
    """Admin ignores field/record scope constraints."""
    from app.services import permission_service

    # Add restrictive scopes that would block non-admin
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, admin_user.username, "pw-admin-123")
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
