"""Both points_abuse and spend_abuse risk flags must block points redemption."""
import pytest


def _earn_points(app, member_id, order_id, subtotal, actor_id):
    from app.services import points_service
    points_service.earn_points(
        member_id=member_id, order_id=order_id,
        subtotal=subtotal, actor_id=actor_id,
    )


def test_points_abuse_blocks_redemption(
    app, client, logged_in_staff, seeded_member, staff_user
):
    """A points_abuse flag on the member blocks further redemptions."""
    from app.services import points_service, risk_service

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 100.0,
    })
    order_id = r.get_json()["id"]
    _earn_points(app, seeded_member.id, order_id, 100.0, staff_user.id)

    # Flag the member with points_abuse
    risk_service.flag_member(seeded_member.id, "points_abuse", actor_id=staff_user.id)

    # Redemption must be blocked
    with pytest.raises(points_service.PointsError) as exc:
        points_service.redeem_points(
            member_id=seeded_member.id,
            order_id=order_id,
            points_to_redeem=5,
            order_subtotal=100.0,
            actor_id=staff_user.id,
        )
    assert "points_abuse" in str(exc.value)


def test_spend_abuse_blocks_redemption(
    app, client, logged_in_staff, seeded_member, staff_user
):
    """A spend_abuse flag (e.g. triggered by stored-value debits > $200/day)
    must also block points redemption — prompt says any active high-risk
    flag halts redemptions until admin clears."""
    from app.services import points_service, risk_service

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 100.0,
    })
    order_id = r.get_json()["id"]
    _earn_points(app, seeded_member.id, order_id, 100.0, staff_user.id)

    risk_service.flag_member(seeded_member.id, "spend_abuse", actor_id=staff_user.id)

    with pytest.raises(points_service.PointsError) as exc:
        points_service.redeem_points(
            member_id=seeded_member.id,
            order_id=order_id,
            points_to_redeem=5,
            order_subtotal=100.0,
            actor_id=staff_user.id,
        )
    assert "spend_abuse" in str(exc.value)


def test_redemption_resumes_after_admin_clears(
    app, client, admin_user, seeded_member, staff_user
):
    """After admin clears the flag, redemption proceeds."""
    from app.services import points_service, risk_service

    r = client.post("/api/auth/login", json={
        "username": staff_user.username, "password": "pw-staff-123",
    })
    assert r.status_code == 200
    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 100.0,
    })
    order_id = r.get_json()["id"]
    _earn_points(app, seeded_member.id, order_id, 100.0, staff_user.id)

    risk_service.flag_member(seeded_member.id, "spend_abuse", actor_id=staff_user.id)
    risk_service.clear_member_flags(seeded_member.id, actor_id=admin_user.id)

    # Redemption now succeeds
    entry = points_service.redeem_points(
        member_id=seeded_member.id,
        order_id=order_id,
        points_to_redeem=5,
        order_subtotal=100.0,
        actor_id=staff_user.id,
    )
    assert entry.points == 5


def test_redeem_api_blocked_by_spend_abuse(
    app, client, logged_in_staff, seeded_member, staff_user
):
    """The /api/points/redeem endpoint returns 400 when spend_abuse is active."""
    from app.services import points_service, risk_service

    r = client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 100.0,
    })
    order_id = r.get_json()["id"]
    points_service.earn_points(
        member_id=seeded_member.id, order_id=order_id,
        subtotal=100.0, actor_id=staff_user.id,
    )

    risk_service.flag_member(seeded_member.id, "spend_abuse", actor_id=staff_user.id)

    resp = client.post("/api/points/redeem", json={
        "member_id": seeded_member.id,
        "order_id": order_id,
        "points": 5,
    })
    assert resp.status_code == 400
    assert "spend_abuse" in resp.get_json()["error"]
