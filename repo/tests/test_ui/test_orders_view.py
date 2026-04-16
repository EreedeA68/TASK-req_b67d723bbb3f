"""Orders HTMX view tests — error paths for create form."""


def test_orders_create_page_renders(client, logged_in_staff):
    resp = client.get("/orders/create")
    assert resp.status_code == 200
    assert b"order" in resp.data.lower()


def test_orders_create_missing_member_id_returns_400(client, logged_in_staff):
    resp = client.post("/orders/create", data={"subtotal": "10.0"})
    assert resp.status_code == 400
    assert b"member_id" in resp.data.lower()


def test_orders_create_missing_subtotal_returns_400(client, logged_in_staff, seeded_member):
    resp = client.post("/orders/create", data={"member_id": seeded_member.id})
    assert resp.status_code == 400
    assert b"subtotal" in resp.data.lower()


def test_orders_create_invalid_member_id_returns_400(client, logged_in_staff):
    resp = client.post("/orders/create", data={"member_id": "abc", "subtotal": "10.0"})
    assert resp.status_code == 400


def test_orders_create_success(client, logged_in_staff, seeded_member):
    resp = client.post("/orders/create", data={
        "member_id": seeded_member.id,
        "subtotal": "15.00",
        "discount": "0",
    })
    assert resp.status_code in (200, 302)


def test_orders_detail_page_renders(client, logged_in_staff, seeded_member):
    r = client.post("/api/orders", json={"member_id": seeded_member.id, "subtotal": 10.0})
    oid = r.get_json()["id"]
    resp = client.get(f"/orders/{oid}")
    assert resp.status_code == 200
    assert b"order" in resp.data.lower()


def test_orders_detail_not_found(client, logged_in_staff):
    resp = client.get("/orders/99999")
    assert resp.status_code == 404


def test_orders_pay_not_found(client, logged_in_staff):
    resp = client.post("/orders/99999/pay", data={})
    assert resp.status_code == 404


def test_orders_pay_success(client, logged_in_staff, seeded_member):
    r = client.post("/api/orders", json={"member_id": seeded_member.id, "subtotal": 10.0})
    oid = r.get_json()["id"]
    resp = client.post(f"/orders/{oid}/pay", data={"redeem_points": "0"})
    assert resp.status_code == 200


def test_orders_pay_already_paid_returns_400(client, logged_in_staff, seeded_member):
    r = client.post("/api/orders", json={"member_id": seeded_member.id, "subtotal": 10.0})
    oid = r.get_json()["id"]
    client.post(f"/orders/{oid}/pay", data={})
    resp = client.post(f"/orders/{oid}/pay", data={})
    assert resp.status_code == 400


def test_orders_advance_not_found(client, logged_in_staff):
    resp = client.post("/orders/99999/advance", data={})
    assert resp.status_code == 404


def test_orders_advance_success(client, logged_in_staff, seeded_member):
    r = client.post("/api/orders", json={"member_id": seeded_member.id, "subtotal": 10.0})
    oid = r.get_json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={})
    resp = client.post(f"/orders/{oid}/advance", data={})
    assert resp.status_code == 200


def test_orders_advance_final_state_returns_400(app, client, logged_in_staff, seeded_member):
    from app.services import order_service
    from app.db import db

    r = client.post("/api/orders", json={"member_id": seeded_member.id, "subtotal": 10.0})
    oid = r.get_json()["id"]
    # Force order into cancelled (final) state via service, then try to advance
    order = order_service.get_by_id(oid)
    order.status = "cancelled"
    db.session.commit()
    resp = client.post(f"/orders/{oid}/advance", data={})
    assert resp.status_code == 400
