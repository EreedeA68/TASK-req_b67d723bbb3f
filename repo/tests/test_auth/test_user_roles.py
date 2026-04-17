"""Admin user-role management tests."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_list_users_requires_admin(client, logged_in_staff):
    resp = client.get("/api/users")
    assert resp.status_code == 403


def test_list_users_admin(client, logged_in_admin, staff_user):
    resp = client.get("/api/users")
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.get_json()["results"]]
    assert "admin1" in usernames
    assert "staff1" in usernames


def test_assign_roles_replaces_roles(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.put(f"/api/users/{staff_user.id}/roles", json={
        "roles": ["admin", "photographer"],
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data["roles"]) == {"admin", "photographer"}


def test_add_role(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.post(f"/api/users/{staff_user.id}/roles", json={
        "role": "kitchen",
    })
    assert resp.status_code == 200
    assert "kitchen" in resp.get_json()["roles"]
    assert "staff" in resp.get_json()["roles"]


def test_remove_role(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    client.post(f"/api/users/{staff_user.id}/roles", json={"role": "kitchen"})
    resp = client.delete(f"/api/users/{staff_user.id}/roles/kitchen", json={})
    assert resp.status_code == 200
    assert "kitchen" not in resp.get_json()["roles"]


def test_assign_roles_unknown_role(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.put(f"/api/users/{staff_user.id}/roles", json={
        "roles": ["bogus_role"],
    })
    assert resp.status_code == 400


def test_assign_roles_user_not_found(app, client, admin_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.put("/api/users/99999/roles", json={"roles": ["staff"]})
    assert resp.status_code == 404


def test_non_admin_cannot_assign_roles(client, logged_in_staff, staff_user):
    resp = client.put(f"/api/users/{staff_user.id}/roles", json={
        "roles": ["admin"],
    })
    assert resp.status_code == 403


def test_add_role_missing_field_returns_400(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.post(f"/api/users/{staff_user.id}/roles", json={})
    assert resp.status_code == 400


def test_add_role_user_not_found_returns_404(app, client, admin_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.post("/api/users/99999/roles", json={"role": "staff"})
    assert resp.status_code == 404


def test_remove_role_user_not_found_returns_404(app, client, admin_user):
    _login(client, admin_user.username, "pw-admin-123")
    resp = client.delete("/api/users/99999/roles/staff", json={})
    assert resp.status_code == 404


def test_remove_role_success(app, client, admin_user, staff_user):
    _login(client, admin_user.username, "pw-admin-123")
    client.post(f"/api/users/{staff_user.id}/roles", json={"role": "kitchen"})
    resp = client.delete(f"/api/users/{staff_user.id}/roles/kitchen", json={})
    assert resp.status_code == 200


def test_role_change_audited(app, client, admin_user, staff_user):
    from app.models.audit import AuditLog

    _login(client, admin_user.username, "pw-admin-123")
    client.put(f"/api/users/{staff_user.id}/roles", json={"roles": ["photographer"]})
    logs = AuditLog.query.filter_by(action="user_roles_assigned").all()
    assert len(logs) >= 1
