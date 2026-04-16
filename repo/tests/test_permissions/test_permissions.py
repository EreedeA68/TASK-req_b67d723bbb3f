"""Tests for the configurable hybrid RBAC/ABAC permission system."""


def test_grant_permission(app, admin_user):
    """Granting a permission creates a ScopePermission record."""
    from app.services import permission_service

    perm = permission_service.grant_permission(
        role_name="staff",
        resource="order",
        action="view",
        scope_type="location",
        scope_value="main",
        actor_id=admin_user.id,
    )
    assert perm.id is not None
    assert perm.role_name == "staff"
    assert perm.resource == "order"
    assert perm.action == "view"
    assert perm.scope_type == "location"
    assert perm.scope_value == "main"
    assert perm.granted is True
    assert perm.created_by == admin_user.id


def test_revoke_permission(app, admin_user):
    """Revoking a permission removes the ScopePermission record."""
    from app.services import permission_service

    perm = permission_service.grant_permission(
        role_name="staff",
        resource="order",
        action="view",
        actor_id=admin_user.id,
    )
    perm_id = perm.id

    result = permission_service.revoke_permission(perm_id, actor_id=admin_user.id)
    assert result is True

    # The record should no longer exist.
    remaining = permission_service.list_permissions(role_name="staff")
    assert all(p.id != perm_id for p in remaining)

    # Revoking a non-existent id returns False.
    assert permission_service.revoke_permission(999999) is False


def test_list_permissions(app, admin_user):
    """list_permissions returns all records, or filters by role."""
    from app.services import permission_service

    permission_service.grant_permission("staff", "order", "view", actor_id=admin_user.id)
    permission_service.grant_permission("kitchen", "kds", "view", actor_id=admin_user.id)
    permission_service.grant_permission("staff", "member", "view", actor_id=admin_user.id)

    all_perms = permission_service.list_permissions()
    assert len(all_perms) == 3

    staff_perms = permission_service.list_permissions(role_name="staff")
    assert len(staff_perms) == 2
    assert all(p.role_name == "staff" for p in staff_perms)


def test_scope_check_passes(app, staff_user):
    """check_scope passes when the context matches a scope record."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff",
        resource="order",
        action="view",
        scope_type="location",
        scope_value="main",
    )

    result = permission_service.check_scope(
        staff_user, "order", "view", context={"location": "main"},
    )
    assert result is True


def test_scope_check_denied(app, staff_user):
    """check_scope denies when scope records exist but none match the context."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff",
        resource="order",
        action="view",
        scope_type="location",
        scope_value="main",
    )

    # Context has a different location value.
    result = permission_service.check_scope(
        staff_user, "order", "view", context={"location": "branch"},
    )
    assert result is False

    # No context at all should also be denied when scoped records exist.
    result_no_ctx = permission_service.check_scope(
        staff_user, "order", "view", context={},
    )
    assert result_no_ctx is False


def test_scope_check_no_records_allows(app, staff_user):
    """When no scope records exist, check_scope returns True (no constraints)."""
    from app.services import permission_service

    result = permission_service.check_scope(
        staff_user, "order", "view", context={"location": "main"},
    )
    assert result is True


def test_scope_check_unrestricted_grant(app, staff_user):
    """A scope record with scope_type=None is an unrestricted grant."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff",
        resource="order",
        action="view",
        scope_type=None,
        scope_value=None,
    )

    result = permission_service.check_scope(
        staff_user, "order", "view", context={"location": "anywhere"},
    )
    assert result is True


def test_non_admin_cannot_manage_permissions(client, logged_in_staff):
    """A non-admin user receives 403 on permission management endpoints."""
    # GET /api/permissions — view
    resp = client.get("/api/permissions")
    assert resp.status_code == 403

    # POST /api/permissions — manage
    resp = client.post(
        "/api/permissions",
        json={"role_name": "staff", "resource": "order", "action": "view"},
    )
    assert resp.status_code == 403

    # DELETE /api/permissions/1 — manage
    resp = client.delete("/api/permissions/1", json={})
    assert resp.status_code == 403


def test_permission_change_audited(app, admin_user):
    """Granting and revoking permissions both produce audit log entries."""
    from app.models.audit import AuditLog
    from app.services import permission_service

    perm = permission_service.grant_permission(
        role_name="staff",
        resource="order",
        action="view",
        scope_type="station",
        scope_value="grill",
        actor_id=admin_user.id,
    )

    grant_logs = AuditLog.query.filter_by(action="permission_granted").all()
    assert len(grant_logs) == 1
    assert "staff" in grant_logs[0].get_metadata().get("role_name", "")

    permission_service.revoke_permission(perm.id, actor_id=admin_user.id)

    revoke_logs = AuditLog.query.filter_by(action="permission_revoked").all()
    assert len(revoke_logs) == 1


def test_api_grant_and_list(client, logged_in_admin):
    """Admin can grant and list permissions via the API."""
    resp = client.post(
        "/api/permissions",
        json={
            "role_name": "staff",
            "resource": "order",
            "action": "view",
            "scope_type": "location",
            "scope_value": "main",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["role_name"] == "staff"
    perm_id = data["id"]

    resp = client.get("/api/permissions")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert any(p["id"] == perm_id for p in results)


def test_api_revoke(client, logged_in_admin):
    """Admin can revoke a permission via the API."""
    resp = client.post(
        "/api/permissions",
        json={"role_name": "staff", "resource": "order", "action": "view"},
    )
    perm_id = resp.get_json()["id"]

    resp = client.delete(f"/api/permissions/{perm_id}", json={})
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] is True

    # Verify it's gone.
    resp = client.get("/api/permissions")
    results = resp.get_json()["results"]
    assert not any(p["id"] == perm_id for p in results)


def test_api_revoke_not_found(client, logged_in_admin):
    """Revoking a non-existent permission returns 404."""
    resp = client.delete("/api/permissions/999999", json={})
    assert resp.status_code == 404


def test_api_grant_missing_fields(client, logged_in_admin):
    """Granting with missing required fields returns 400."""
    resp = client.post("/api/permissions", json={"role_name": "staff"})
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"]


def test_has_permission_with_scope(app, staff_user):
    """has_permission integrates static RBAC with scope constraints."""
    from app.core.rbac import has_permission
    from app.services import permission_service

    # Staff has static RBAC for order:view. No scope records => allowed.
    assert has_permission(staff_user, "order", "view") is True

    # Add a scope constraint limiting order:view to location=main.
    permission_service.grant_permission(
        role_name="staff",
        resource="order",
        action="view",
        scope_type="location",
        scope_value="main",
    )

    # Without context, the scope check should fail (records exist but none match).
    assert has_permission(staff_user, "order", "view") is False

    # With matching context, it passes.
    assert has_permission(staff_user, "order", "view", context={"location": "main"}) is True

    # With non-matching context, it fails.
    assert has_permission(staff_user, "order", "view", context={"location": "branch"}) is False
