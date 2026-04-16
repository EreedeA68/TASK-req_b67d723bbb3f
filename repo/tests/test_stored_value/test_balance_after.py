"""Stored-value history includes computed balance_after per entry."""


def test_balance_after_computed_for_admin(
    app, client, admin_user, seeded_member
):
    """Admin sees raw balance_after values that reflect running totals."""
    from app.services import stored_value_service

    stored_value_service.credit(
        member_id=seeded_member.id, amount=100.0,
        description="seed", actor_id=admin_user.id,
    )
    stored_value_service.debit(
        member_id=seeded_member.id, amount=30.0,
        actor_id=admin_user.id,
    )
    stored_value_service.credit(
        member_id=seeded_member.id, amount=10.0,
        description="top-up", actor_id=admin_user.id,
    )

    client.post("/api/auth/login", json={
        "username": admin_user.username, "password": "pw-admin-123",
    })
    resp = client.get(f"/api/stored-value/history/{seeded_member.id}")
    assert resp.status_code == 200
    # Results are newest-first
    results = resp.get_json()["results"]
    assert len(results) == 3
    # Newest-first: last credit (+10), debit (-30), first credit (+100)
    assert results[0]["balance_after"] == 80.0  # 100 - 30 + 10
    assert results[1]["balance_after"] == 70.0  # 100 - 30
    assert results[2]["balance_after"] == 100.0  # +100


def test_balance_after_masked_for_non_admin(
    app, client, staff_user, admin_user, seeded_member
):
    """Non-admin sees masked balance_after values."""
    from app.services import stored_value_service

    stored_value_service.credit(
        member_id=seeded_member.id, amount=50.0,
        description="seed", actor_id=admin_user.id,
    )

    client.post("/api/auth/login", json={
        "username": staff_user.username, "password": "pw-staff-123",
    })
    resp = client.get(f"/api/stored-value/history/{seeded_member.id}")
    assert resp.status_code == 200
    for entry in resp.get_json()["results"]:
        assert entry["balance_after"] == "****"
