"""Content-type enforcement for bodyless mutating API calls (CSRF defence).

Closes the gap where a cross-site form POST with no body could trigger
state-changing endpoints like /api/auth/logout under a victim's session.
"""


def test_bodyless_logout_rejected_without_json_ct(client, logged_in_staff):
    """POST /api/auth/logout with no Content-Type is rejected with 415."""
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 415
    assert "Content-Type" in resp.get_json()["error"]


def test_bodyless_logout_rejected_with_form_ct(client, logged_in_staff):
    """Form-encoded POST to /api/auth/logout (even empty) is rejected."""
    resp = client.post(
        "/api/auth/logout",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 415


def test_bodyless_logout_allowed_with_json_ct(client, logged_in_staff):
    """Explicit JSON content-type allows bodyless logout."""
    resp = client.post("/api/auth/logout", json={})
    assert resp.status_code == 200


def test_bodyless_order_pay_rejected_without_json_ct(
    client, logged_in_staff, seeded_member
):
    """Bodyless POST to /api/orders/{id}/pay also requires JSON CT."""
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    order_id = r.get_json()["id"]
    # Bodyless pay
    resp = client.post(f"/api/orders/{order_id}/pay")
    assert resp.status_code == 415


def test_bodyless_delete_rejected_without_json_ct(
    client, logged_in_admin, staff_user
):
    """DELETE without JSON CT is also rejected."""
    resp = client.delete(f"/api/users/{staff_user.id}/roles/staff")
    assert resp.status_code == 415
