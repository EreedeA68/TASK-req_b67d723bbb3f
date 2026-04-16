"""Record-scope enforcement on stored-value credit/debit endpoints."""


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_credit_denied_when_out_of_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Credit blocked when record-scope excludes the target member."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/stored-value/credit", json={
        "member_id": seeded_member.id, "amount": 50.0,
    })
    assert resp.status_code == 403


def test_debit_denied_when_out_of_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Debit blocked when record-scope excludes the target member."""
    from app.services import permission_service, stored_value_service

    # Seed some balance first as admin
    stored_value_service.credit(
        member_id=seeded_member.id, amount=100.0,
        description="seed", actor_id=admin_user.id,
    )

    # Restrict staff scope
    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value="99999",
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/stored-value/debit", json={
        "member_id": seeded_member.id, "amount": 20.0,
    })
    assert resp.status_code == 403


def test_credit_allowed_when_in_scope(
    app, client, staff_user, admin_user, seeded_member
):
    """Credit succeeds when record-scope matches."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff", resource="member", action="view",
        scope_type="record", scope_value=str(seeded_member.id),
        actor_id=admin_user.id,
    )

    _login(client, staff_user.username, "pw-staff-123")
    resp = client.post("/api/stored-value/credit", json={
        "member_id": seeded_member.id, "amount": 25.0,
    })
    assert resp.status_code == 200
