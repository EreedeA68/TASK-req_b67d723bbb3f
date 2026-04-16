"""Tests that the correction submission view requires correction:submit permission."""


def test_correction_view_requires_auth(client):
    """Unauthenticated user redirected/forbidden."""
    resp = client.post("/clock-in/correction", data={
        "punch_type": "clock_in",
        "requested_time": "2026-01-01T09:00:00",
        "reason": "forgot",
    })
    # View layer returns 302 redirect or 403 for unauth
    assert resp.status_code in (302, 401, 403)


def test_correction_view_denied_for_user_without_permission(
    app, client, seeded_member
):
    """A user without correction:submit permission gets 403."""
    from app.models.user import User
    from app.services import auth_service

    # Register a user WITHOUT any correction-capable role (member-only)
    auth_service.register("member_only", "pw-member-123", roles=["member"])

    client.post("/api/auth/login", json={
        "username": "member_only", "password": "pw-member-123",
    })

    resp = client.post("/clock-in/correction", data={
        "punch_type": "clock_in",
        "requested_time": "2026-01-01T09:00:00",
        "reason": "forgot to punch in",
    })
    assert resp.status_code == 403


def test_correction_view_allowed_for_staff(client, logged_in_staff):
    """Staff has correction:submit permission."""
    resp = client.post("/clock-in/correction", data={
        "punch_type": "clock_in",
        "requested_time": "2026-01-01T09:00:00",
        "reason": "forgot to punch in",
    })
    # Should not be forbidden
    assert resp.status_code != 403
