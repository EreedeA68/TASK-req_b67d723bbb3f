"""Member API tests."""

# Known plaintext phone for seeded_member (created in conftest).
SEEDED_PHONE = "5551234567"


def test_create_member_requires_auth(client, app):
    from app.models.audit import AuditLog

    resp = client.post(
        "/api/members",
        json={"name": "Bob", "phone_number": "5550001"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication required"
    unauth = AuditLog.query.filter_by(action="unauthorized_access").count()
    assert unauth == 1


def test_create_member_as_staff(client, logged_in_staff, app):
    from app.models.audit import AuditLog
    from app.models.member import Member

    resp = client.post(
        "/api/members",
        json={
            "name": "Alice",
            "phone_number": "5551111111",
            "member_id": "M-ALICE01",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["member_id"] == "M-ALICE01"
    assert data["name"] == "Alice"
    # Staff sees masked phone
    assert data["phone_number"] == "****1111"
    assert data["points_balance"] == 0
    assert data["tier"] == "standard"
    # DB state — phone stored encrypted
    m = Member.query.filter_by(member_id="M-ALICE01").first()
    assert m is not None
    assert m.phone_number != "5551111111"  # encrypted
    # Audit
    entries = AuditLog.query.filter_by(action="member_created").all()
    assert any(e.get_metadata()["member_id"] == "M-ALICE01" for e in entries)


def test_search_member_by_phone(client, logged_in_staff, seeded_member, app):
    from app.models.audit import AuditLog

    resp = client.get(f"/api/members/search?q={SEEDED_PHONE}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["match"] == "exact"
    assert len(data["results"]) == 1
    assert data["results"][0]["member_id"] == seeded_member.member_id
    # Audit trail
    lookups = AuditLog.query.filter_by(action="member_lookup").all()
    assert any(e.get_metadata().get("found") is True for e in lookups)


def test_search_member_by_member_id(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/members/search?q={seeded_member.member_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["match"] == "exact"
    assert data["results"][0]["id"] == seeded_member.id


def test_search_member_not_found(client, logged_in_staff):
    resp = client.get("/api/members/search?q=NOPE")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["results"] == []
    assert body["match"] == "partial"


def test_search_member_empty_query_rejected(client, logged_in_staff):
    resp = client.get("/api/members/search?q=")
    assert resp.status_code == 400
    assert "empty" in resp.get_json()["error"].lower()


def test_search_member_whitespace_query_rejected(client, logged_in_staff):
    resp = client.get("/api/members/search?q=%20%20")
    assert resp.status_code == 400


def test_get_member_by_id(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == seeded_member.id
    assert data["member_id"] == seeded_member.member_id


def test_get_member_by_id_404(client, logged_in_staff):
    resp = client.get("/api/members/99999")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "member not found"


def test_create_member_missing_fields(client, logged_in_staff):
    resp = client.post("/api/members", json={"name": "NoPhone"})
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"]


def test_create_member_empty_name_rejected(client, logged_in_staff):
    resp = client.post(
        "/api/members",
        json={"name": "   ", "phone_number": "5550002"},
    )
    assert resp.status_code == 400


def test_create_member_permission_denied_for_kitchen(client, logged_in_kitchen, app):
    """Kitchen role cannot create members."""
    from app.models.audit import AuditLog

    resp = client.post(
        "/api/members",
        json={"name": "Forbidden", "phone_number": "5559999"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"
    denials = AuditLog.query.filter_by(action="permission_denied").all()
    assert len(denials) == 1


def test_member_search_allowed_for_photographer(client, seeded_member, app):
    """Photographer role can search members (read-only)."""
    from app.services import auth_service

    auth_service.register("photog", "photo-pw-1", roles=["photographer"])
    client.post(
        "/api/auth/login",
        json={"username": "photog", "password": "photo-pw-1"},
    )
    resp = client.get(f"/api/members/search?q={seeded_member.member_id}")
    assert resp.status_code == 200
