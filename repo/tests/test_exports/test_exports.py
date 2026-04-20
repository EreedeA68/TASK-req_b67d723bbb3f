"""Export system tests."""
import os


def test_export_requires_auth(client):
    resp = client.post("/api/exports", json={"type": "orders"})
    assert resp.status_code == 401


def test_export_orders(client, logged_in_staff, seeded_member, app):
    from app.models.audit import AuditLog

    # Create an order to export
    client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    resp = client.post("/api/exports", json={"type": "orders"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["type"] == "orders"
    assert data["file_path"] is not None
    # File exists
    assert os.path.exists(data["file_path"])
    # Audit
    assert AuditLog.query.filter_by(action="export_completed").count() == 1


def test_export_members(client, logged_in_staff, seeded_member, app):
    # Create an order so staff has an interaction with this member (scope requirement)
    client.post("/api/orders", json={"member_id": seeded_member.id, "subtotal": 5.0})
    resp = client.post("/api/exports", json={"type": "members"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert os.path.exists(data["file_path"])
    # CSV contains member data
    with open(data["file_path"]) as f:
        content = f.read()
    assert "M-TEST0001" in content


def test_export_bookings(client, logged_in_staff, app):
    resp = client.post("/api/exports", json={"type": "bookings"})
    assert resp.status_code == 201


def test_export_invalid_type_rejected(client, logged_in_staff):
    resp = client.post("/api/exports", json={"type": "invalid"})
    assert resp.status_code == 400
    assert "invalid" in resp.get_json()["error"].lower()


def test_list_exports(client, logged_in_staff, app):
    client.post("/api/exports", json={"type": "orders"})
    resp = client.get("/api/exports")
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) == 1


def test_export_ui_page(client, logged_in_staff):
    resp = client.get("/exports")
    assert resp.status_code == 200
    assert b"Exports" in resp.data


def test_export_ui_create(client, logged_in_staff, app):
    resp = client.post("/exports/create", data={"type": "orders"})
    assert resp.status_code == 200
    assert b"export-row" in resp.data


def test_export_ui_create_invalid_type_returns_400(client, logged_in_staff):
    resp = client.post("/exports/create", data={"type": "invalid_type"})
    assert resp.status_code == 400
    assert b"Exports" in resp.data
