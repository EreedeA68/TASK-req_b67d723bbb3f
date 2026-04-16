"""HTML/HTMX frontend tests using Flask's test client."""


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Login" in resp.data
    assert b'name="username"' in resp.data
    assert b'name="password"' in resp.data


def test_members_page_requires_auth_redirects(client, app):
    from app.models.audit import AuditLog

    resp = client.get("/members")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")
    unauth = AuditLog.query.filter_by(action="unauthorized_access").all()
    assert any("/members" in e.resource for e in unauth)


def test_members_page_renders_when_logged_in(client, logged_in_staff):
    resp = client.get("/members")
    assert resp.status_code == 200
    assert b"Member Lookup" in resp.data
    assert b"hx-get" in resp.data
    assert b"/members/lookup" in resp.data


def test_member_lookup_partial_empty_query(client, logged_in_staff):
    """Empty query returns a partial, not a full page, not a 4xx."""
    resp = client.get("/members/lookup?q=")
    assert resp.status_code == 200
    # Empty-state partial: no <html> shell, but the placeholder text is present.
    assert b"<html" not in resp.data
    assert b"Start typing" in resp.data


def test_member_lookup_partial_found(client, logged_in_staff, seeded_member):
    resp = client.get(f"/members/lookup?q={seeded_member.member_id}")
    assert resp.status_code == 200
    # Must be a partial, not a full page
    assert b"<html" not in resp.data
    assert seeded_member.member_id.encode() in resp.data
    assert b"member-card" in resp.data


def test_member_lookup_partial_not_found(client, logged_in_staff):
    resp = client.get("/members/lookup?q=ZZZNOTFOUND")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"No member found" in resp.data


def test_member_lookup_requires_auth(client):
    resp = client.get("/members/lookup?q=abc")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_order_create_page_renders(client, logged_in_staff, seeded_member):
    resp = client.get("/orders/create")
    assert resp.status_code == 200
    assert b"Create Order" in resp.data
    assert seeded_member.member_id.encode() in resp.data


def test_order_create_page_requires_auth(client):
    resp = client.get("/orders/create")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_order_detail_page_renders(
    client, logged_in_staff, seeded_member, app
):
    from app.services import order_service

    order = order_service.create_order(
        member_id=seeded_member.id, subtotal=30.0
    )
    resp = client.get(f"/orders/{order.id}")
    assert resp.status_code == 200
    assert b"created" in resp.data
    assert b"Pay" in resp.data
    assert b"hx-post" in resp.data
    assert f"/orders/{order.id}/pay".encode() in resp.data


def test_order_pay_htmx_partial(client, logged_in_staff, seeded_member, app):
    from app.services import order_service

    order = order_service.create_order(
        member_id=seeded_member.id, subtotal=30.0
    )
    resp = client.post(f"/orders/{order.id}/pay")
    assert resp.status_code == 200
    # Must be a partial, not a full page
    assert b"<html" not in resp.data
    assert b"paid" in resp.data
    assert b"Advance Status" in resp.data


def test_order_advance_htmx_partial(
    client, logged_in_staff, seeded_member, app
):
    from app.services import order_service

    order = order_service.create_order(
        member_id=seeded_member.id, subtotal=30.0
    )
    order_service.pay(order)
    resp = client.post(f"/orders/{order.id}/advance")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"in_prep" in resp.data


def test_order_pay_duplicate_returns_partial(
    client, logged_in_staff, seeded_member, app
):
    """Duplicate pay via HTMX returns an error partial, not a full page."""
    from app.services import order_service

    order = order_service.create_order(
        member_id=seeded_member.id, subtotal=10.0
    )
    order_service.pay(order)
    resp = client.post(f"/orders/{order.id}/pay")
    assert resp.status_code == 400
    assert b"<html" not in resp.data
    body = resp.data.lower()
    assert b"duplicate" in body or b"already" in body


def test_order_advance_past_final_returns_partial(
    client, logged_in_staff, seeded_member, app
):
    from app.services import order_service

    order = order_service.create_order(
        member_id=seeded_member.id, subtotal=10.0
    )
    order_service.pay(order)
    for _ in range(4):
        order_service.advance(order)
    assert order.status == "reviewed"

    resp = client.post(f"/orders/{order.id}/advance")
    assert resp.status_code == 400
    assert b"<html" not in resp.data
    assert b"final" in resp.data.lower()


def test_order_create_form_submit(client, logged_in_staff, seeded_member):
    resp = client.post(
        "/orders/create",
        data={"member_id": seeded_member.id, "subtotal": "42.50"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/orders/" in resp.headers.get("Location", "")


def test_order_create_form_negative_subtotal_rejected(
    client, logged_in_staff, seeded_member
):
    resp = client.post(
        "/orders/create",
        data={"member_id": seeded_member.id, "subtotal": "-5"},
    )
    assert resp.status_code == 400
    assert b"Create Order" in resp.data  # re-renders the form


def test_login_via_form(client, app):
    from app.services import auth_service

    auth_service.register("ui-user", "ui-pass-1", roles=["staff"])
    resp = client.post(
        "/auth/login",
        data={"username": "ui-user", "password": "ui-pass-1"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # Session should now grant access
    resp = client.get("/members")
    assert resp.status_code == 200


def test_login_htmx_redirect_header(client, app):
    from app.services import auth_service

    auth_service.register("htmx-user", "hxpass-1", roles=["staff"])
    resp = client.post(
        "/auth/login",
        data={"username": "htmx-user", "password": "hxpass-1"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect", "").endswith("/members")
    # Response body should be a partial, not a full page
    assert b"<html" not in resp.data


def test_login_error_renders_partial_on_htmx(client):
    resp = client.post(
        "/auth/login",
        data={"username": "ghost", "password": "wrong"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 401
    assert b"<html" not in resp.data
    assert b"invalid credentials" in resp.data


def test_ui_logout_requires_auth(client):
    """POST /auth/logout is login_required."""
    resp = client.post("/auth/logout")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_ui_logout_invalidates_session(client, app):
    from app.services import auth_service

    auth_service.register("lo-user", "lo-pass-1", roles=["staff"])
    client.post(
        "/auth/login",
        data={"username": "lo-user", "password": "lo-pass-1"},
    )
    # Access granted
    assert client.get("/members").status_code == 200
    # Logout
    resp = client.post("/auth/logout", follow_redirects=False)
    assert resp.status_code == 302
    # Access denied
    assert client.get("/members").status_code == 302


def test_ui_forbidden_for_insufficient_role(client, app):
    """Kitchen role cannot open order creation UI."""
    from app.services import auth_service

    auth_service.register("k-ui", "k-ui-pw-1", roles=["kitchen"])
    client.post(
        "/api/auth/login",
        json={"username": "k-ui", "password": "k-ui-pw-1"},
    )
    resp = client.get("/orders/create")
    assert resp.status_code == 403
    assert b"Forbidden" in resp.data
