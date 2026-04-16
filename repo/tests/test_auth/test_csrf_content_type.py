"""Tests for JSON content-type enforcement on mutating API endpoints (CSRF defense)."""


def test_form_encoded_post_rejected(client, logged_in_staff, seeded_member):
    """POST with form-encoded body to mutating API endpoint is rejected (415)."""
    resp = client.post(
        "/api/orders",
        data=f"member_id={seeded_member.id}&subtotal=10.0",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 415
    assert "Content-Type" in resp.get_json()["error"]


def test_multipart_post_rejected(client, logged_in_staff, seeded_member):
    """POST with multipart form data is rejected (415)."""
    resp = client.post(
        "/api/orders",
        data={"member_id": str(seeded_member.id), "subtotal": "10.0"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 415


def test_text_plain_post_rejected(client, logged_in_staff, seeded_member):
    """POST with text/plain body is rejected (415)."""
    resp = client.post(
        "/api/orders",
        data='{"member_id":1,"subtotal":10.0}',
        content_type="text/plain",
    )
    assert resp.status_code == 415


def test_json_post_allowed(client, logged_in_staff, seeded_member):
    """POST with application/json is allowed."""
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    assert resp.status_code == 201


def test_get_endpoints_not_content_type_restricted(client, logged_in_staff):
    """GET endpoints have no content-type restriction."""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
