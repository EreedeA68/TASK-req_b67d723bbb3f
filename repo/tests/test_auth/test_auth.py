"""Auth API + service tests."""


def _register(client, username="alice", password="secret-1"):
    payload = {"username": username, "password": password}
    return client.post("/api/auth/register", json=payload)


def test_register_creates_user(client, app):
    from app.models.user import User

    resp = _register(client, username="alice")
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["username"] == "alice"
    # Public registration assigns "member" role only
    assert "member" in data["roles"]
    assert "id" in data
    # DB state
    user = User.query.filter_by(username="alice").first()
    assert user is not None
    assert user.has_role("member")


def test_register_ignores_client_supplied_roles(client, app):
    """Public registration must not allow privilege escalation via roles."""
    resp = client.post(
        "/api/auth/register",
        json={"username": "attacker", "password": "pw-123", "roles": ["admin"]},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert "admin" not in data["roles"]
    assert "member" in data["roles"]


def test_register_duplicate_username_rejected(client):
    _register(client, username="bob", password="pw12345")
    resp = _register(client, username="bob", password="pw12345")
    assert resp.status_code == 400
    assert "already exists" in resp.get_json()["error"]


def test_register_missing_fields_rejected(client):
    resp = client.post("/api/auth/register", json={"username": "only"})
    assert resp.status_code == 400


def test_login_success(client):
    _register(client, username="carol", password="good-password")
    resp = client.post(
        "/api/auth/login",
        json={"username": "carol", "password": "good-password"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["username"] == "carol"
    assert body["message"] == "logged in"


def test_login_wrong_password(client, app):
    from app.models.audit import AuditLog

    _register(client, username="dave", password="correct-pw")
    resp = client.post(
        "/api/auth/login",
        json={"username": "dave", "password": "wrong-pw"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid credentials"
    # Audit log: a "login_failed" entry exists with reason=bad_password.
    entries = AuditLog.query.filter_by(action="login_failed").all()
    assert len(entries) == 1
    md = entries[0].get_metadata()
    assert md.get("reason") == "bad_password"
    assert md.get("username") == "dave"


def test_login_unknown_user_audited(client, app):
    from app.models.audit import AuditLog

    resp = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "whatever"},
    )
    assert resp.status_code == 401
    entries = AuditLog.query.filter_by(action="login_failed").all()
    assert len(entries) == 1
    assert entries[0].get_metadata()["reason"] == "unknown_user"


def test_logout_requires_auth(client, app):
    from app.models.audit import AuditLog

    resp = client.post("/api/auth/logout", json={})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication required"
    # Unauthorized access attempt is audited.
    unauth = AuditLog.query.filter_by(action="unauthorized_access").all()
    assert len(unauth) == 1
    assert "/api/auth/logout" in unauth[0].resource


def test_logout_after_login_clears_session(client, app):
    _register(client, username="erin", password="erin-password")
    client.post(
        "/api/auth/login",
        json={"username": "erin", "password": "erin-password"},
    )
    resp = client.post("/api/auth/logout", json={})
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "logged out"
    # After logout, protected endpoints deny again.
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_endpoint_requires_login(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_endpoint_returns_user(client, logged_in_staff):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.get_json()["username"] == logged_in_staff.username
    assert "staff" in resp.get_json()["roles"]


def test_password_is_hashed(client, app):
    from app.models.user import User

    _register(client, username="frank", password="plaintext-pw")
    user = User.query.filter_by(username="frank").first()
    assert user is not None
    assert user.password_hash != "plaintext-pw"
    assert user.password_hash.startswith("$2")  # bcrypt prefix


def test_audit_log_on_login(client, app):
    from app.models.audit import AuditLog

    _register(client, username="grace", password="grace-password")
    client.post(
        "/api/auth/login",
        json={"username": "grace", "password": "grace-password"},
    )
    logins = AuditLog.query.filter_by(action="login").all()
    assert len(logins) == 1
    assert logins[0].get_metadata()["username"] == "grace"


def test_session_invalidated_after_logout(client, app):
    """After logout, a previously authenticated session cannot access protected routes."""
    from app.services import auth_service

    auth_service.register("henry", "pw-henry-1", roles=["staff"])
    client.post(
        "/api/auth/login",
        json={"username": "henry", "password": "pw-henry-1"},
    )
    # Confirm access before logout
    assert client.get("/api/auth/me").status_code == 200
    # Logout and confirm denial
    client.post("/api/auth/logout", json={})
    assert client.get("/api/auth/me").status_code == 401
    # Member lookup also denied
    assert client.get("/api/members/search?q=x").status_code == 401
