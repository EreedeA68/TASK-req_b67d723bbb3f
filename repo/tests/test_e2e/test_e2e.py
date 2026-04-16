"""End-to-end flow tests.

These simulate: register -> login -> create member -> create order -> pay ->
advance through the full lifecycle. Both JSON API paths and the HTMX UI paths
are exercised, and audit/DB state is validated at each step.
"""


def test_full_flow_json_api(client, app):
    from app.models.audit import AuditLog
    from app.models.member import Member
    from app.models.order import Order, OrderEvent
    from app.services import auth_service

    # 1. Register staff user via service (public API does not allow role assignment)
    auth_service.register("e2e_staff", "e2e-pass-1", roles=["staff"])

    # 2. Log in
    resp = client.post(
        "/api/auth/login",
        json={"username": "e2e_staff", "password": "e2e-pass-1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["user"]["username"] == "e2e_staff"

    # 3. Create a member
    resp = client.post(
        "/api/members",
        json={
            "name": "E2E Tester",
            "phone_number": "5559990000",
            "member_id": "M-E2E0001",
        },
    )
    assert resp.status_code == 201
    member = resp.get_json()
    assert Member.query.filter_by(member_id="M-E2E0001").first() is not None

    # 4. Look up the member by phone
    resp = client.get("/api/members/search?q=5559990000")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["match"] == "exact"
    assert body["results"][0]["id"] == member["id"]

    # 5. Create an order for that member (standard tier allows up to 5% discount)
    resp = client.post(
        "/api/orders",
        json={"member_id": member["id"], "subtotal": 100.0, "discount": 5.0},
    )
    assert resp.status_code == 201
    order = resp.get_json()
    assert order["status"] == "created"
    assert order["total"] == 95.0

    # 6. Pay the order
    resp = client.post(f"/api/orders/{order['id']}/pay", json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "paid"

    # 7. Advance through remaining states
    for expected in ["in_prep", "ready", "delivered", "reviewed"]:
        resp = client.post(f"/api/orders/{order['id']}/advance", json={})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == expected

    # 8. Verify persisted state
    from app.db import db

    persisted = db.session.get(Order, order["id"])
    assert persisted.status == "reviewed"
    event_statuses = [
        e.status
        for e in OrderEvent.query.filter_by(order_id=order["id"])
        .order_by(OrderEvent.timestamp)
        .all()
    ]
    assert event_statuses == [
        "created", "paid", "in_prep", "ready", "delivered", "reviewed",
    ]

    # 9. Audit completeness
    actions = {a.action for a in AuditLog.query.all()}
    for expected in {
        "login",
        "member_created",
        "member_lookup",
        "order_created",
        "order_status_change",
    }:
        assert expected in actions


def test_full_flow_htmx_ui(client, app):
    from app.models.order import Order
    from app.services import auth_service

    auth_service.register("ui_staff", "ui-pass-1", roles=["staff"])

    resp = client.post(
        "/auth/login",
        data={"username": "ui_staff", "password": "ui-pass-1"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    resp = client.post(
        "/api/members",
        json={
            "name": "HTMX Tester",
            "phone_number": "5557770000",
            "member_id": "M-HTMX0001",
        },
    )
    member_id = resp.get_json()["id"]

    resp = client.get("/members/lookup?q=5557770000")
    assert resp.status_code == 200
    assert b"<html" not in resp.data  # must be partial
    assert b"M-HTMX0001" in resp.data

    resp = client.post(
        "/orders/create",
        data={"member_id": member_id, "subtotal": "50.00"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    order_id = int(loc.rstrip("/").split("/")[-1])

    resp = client.get(f"/orders/{order_id}")
    assert resp.status_code == 200
    assert b"created" in resp.data

    resp = client.post(f"/orders/{order_id}/pay")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"paid" in resp.data

    for expected in ["in_prep", "ready", "delivered", "reviewed"]:
        resp = client.post(f"/orders/{order_id}/advance")
        assert resp.status_code == 200
        assert b"<html" not in resp.data
        assert expected.encode() in resp.data

    from app.db import db

    assert db.session.get(Order, order_id).status == "reviewed"


def test_audit_trail_after_full_flow(app, client):
    from app.models.audit import AuditLog
    from app.services import auth_service

    auth_service.register("audit_user", "a-pass-1", roles=["staff"])
    client.post(
        "/api/auth/login",
        json={"username": "audit_user", "password": "a-pass-1"},
    )
    client.post(
        "/api/members",
        json={
            "name": "Audit Member",
            "phone_number": "5551112222",
            "member_id": "M-AUDIT01",
        },
    )
    member_id = client.get("/api/members/search?q=M-AUDIT01").get_json()[
        "results"
    ][0]["id"]
    order_id = client.post(
        "/api/orders",
        json={"member_id": member_id, "subtotal": 10.0},
    ).get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    actions = {a.action for a in AuditLog.query.all()}
    for expected in {
        "login",
        "member_created",
        "member_lookup",
        "order_created",
        "order_status_change",
    }:
        assert expected in actions, f"missing audit action: {expected}"


def test_hardening_negative_flows_audit(app, client):
    """Failed login, unauthorized access, permission denial, rejected
    transitions are all audited."""
    from app.models.audit import AuditLog
    from app.services import auth_service

    # Failed login
    client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "bad"},
    )
    # Unauthorized access
    client.get("/api/members/search?q=x")
    # Permission denial — create kitchen user, attempt to create member
    auth_service.register("kitchen_neg", "kp-1", roles=["kitchen"])
    client.post(
        "/api/auth/login",
        json={"username": "kitchen_neg", "password": "kp-1"},
    )
    client.post(
        "/api/members",
        json={"name": "X", "phone_number": "5550001"},
    )

    # Switch to staff user, create + reject transition
    client.post("/api/auth/logout", json={})
    auth_service.register("staff_neg", "sp-1", roles=["staff"])
    client.post(
        "/api/auth/login",
        json={"username": "staff_neg", "password": "sp-1"},
    )
    client.post(
        "/api/members",
        json={
            "name": "T",
            "phone_number": "5552222",
            "member_id": "M-NEG0001",
        },
    )
    m_id = client.get("/api/members/search?q=M-NEG0001").get_json()["results"][0]["id"]
    order_id = client.post(
        "/api/orders",
        json={"member_id": m_id, "subtotal": 5.0},
    ).get_json()["id"]
    # Pay twice — second is duplicate
    client.post(f"/api/orders/{order_id}/pay", json={})
    client.post(f"/api/orders/{order_id}/pay", json={})

    actions = {a.action for a in AuditLog.query.all()}
    assert "login_failed" in actions
    assert "unauthorized_access" in actions
    assert "permission_denied" in actions
    assert "order_transition_rejected" in actions
