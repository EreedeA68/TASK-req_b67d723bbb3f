"""Points economy tests — earn, redeem, expiry, risk flag integration."""
from datetime import datetime, timedelta

import pytest

from app.db import db
from app.models.member import Member
from app.models.points import PointLedger
from app.services import points_service, risk_service
from app.services.points_service import PointsError


def test_earn_points_on_payment(app, client, logged_in_staff, seeded_member):
    """Paying an order should automatically award floor(subtotal) points."""
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 25.75},
    )
    assert resp.status_code == 201
    order_id = resp.get_json()["id"]

    # Pay the order — should trigger points earn
    resp = client.post(f"/api/orders/{order_id}/pay", json={})
    assert resp.status_code == 200

    # Verify ledger entry
    entries = PointLedger.query.filter_by(
        member_id=seeded_member.id, type="earn"
    ).all()
    assert len(entries) == 1
    assert entries[0].points == 25  # floor(25.75)
    assert entries[0].order_id == order_id
    assert entries[0].expires_at is not None

    # Verify member balance updated
    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 25

    # Verify balance via service
    assert points_service.get_balance(seeded_member.id) == 25


def test_redeem_within_cap(app, client, logged_in_staff, seeded_member):
    """Redeeming points within the 20% cap should succeed."""
    # First earn some points
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 100.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 100

    # Create another order and redeem against it (20% of 100 = 20 max)
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 100.0},
    )
    order2_id = resp.get_json()["id"]

    entry = points_service.redeem_points(
        member_id=seeded_member.id,
        order_id=order2_id,
        points_to_redeem=20,
        order_subtotal=100.0,
    )
    assert entry.type == "redeem"
    assert entry.points == 20

    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 80


def test_redeem_exceeds_cap_rejected(app, client, logged_in_staff, seeded_member):
    """Attempting to redeem more than 20% of order subtotal should fail."""
    # Earn 100 points
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 100.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    # Create a second order with subtotal=50 (20% = 10 max)
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 50.0},
    )
    order2_id = resp.get_json()["id"]

    # Try to redeem 15 points (exceeds 20% of 50 = 10)
    with pytest.raises(PointsError, match="20% cap"):
        points_service.redeem_points(
            member_id=seeded_member.id,
            order_id=order2_id,
            points_to_redeem=15,
            order_subtotal=50.0,
        )

    # Balance should be unchanged
    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 100


def test_redeem_insufficient_balance_rejected(
    app, client, logged_in_staff, seeded_member
):
    """Attempting to redeem more points than the balance should fail."""
    # Earn only 10 points
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    # Create a large order (20% of 500 = 100 max, but balance is only 10)
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 500.0},
    )
    order2_id = resp.get_json()["id"]

    with pytest.raises(PointsError, match="insufficient"):
        points_service.redeem_points(
            member_id=seeded_member.id,
            order_id=order2_id,
            points_to_redeem=50,
            order_subtotal=500.0,
        )

    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 10


def test_redeem_blocked_by_risk_flag(app, client, logged_in_staff, seeded_member):
    """A member with an active points_abuse risk flag cannot redeem."""
    # Earn some points
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 100.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    # Flag the member for points abuse
    risk_service.flag_member(seeded_member.id, "points_abuse")

    # Create another order
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 100.0},
    )
    order2_id = resp.get_json()["id"]

    with pytest.raises(PointsError, match="risk flag"):
        points_service.redeem_points(
            member_id=seeded_member.id,
            order_id=order2_id,
            points_to_redeem=10,
            order_subtotal=100.0,
        )

    # After clearing flags, redemption should succeed
    risk_service.clear_member_flags(seeded_member.id)
    entry = points_service.redeem_points(
        member_id=seeded_member.id,
        order_id=order2_id,
        points_to_redeem=10,
        order_subtotal=100.0,
    )
    assert entry.type == "redeem"


def test_points_expiry(app, client, logged_in_staff, seeded_member):
    """Points should expire 365 days after issuance."""
    # Earn points
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 50.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 50

    # Manually backdate the ledger entry to make it expired
    entry = PointLedger.query.filter_by(
        member_id=seeded_member.id, type="earn"
    ).first()
    entry.created_at = datetime.utcnow() - timedelta(days=400)
    entry.expires_at = datetime.utcnow() - timedelta(days=35)
    db.session.commit()

    # Run expiry
    expired = points_service.expire_points(seeded_member.id)
    assert expired == 50

    # Balance should be zero
    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 0

    # get_balance should also return 0
    assert points_service.get_balance(seeded_member.id) == 0


def test_redeem_missing_field_returns_400(client, logged_in_staff):
    resp = client.post("/api/points/redeem", json={"member_id": 1, "order_id": 1})
    assert resp.status_code == 400
    assert "points" in resp.get_json()["error"]


def test_redeem_invalid_type_returns_400(client, logged_in_staff, seeded_member):
    resp = client.post("/api/points/redeem", json={
        "member_id": "abc", "order_id": 1, "points": 10,
    })
    assert resp.status_code == 400


def test_redeem_order_not_found_returns_404(client, logged_in_staff, seeded_member):
    resp = client.post("/api/points/redeem", json={
        "member_id": seeded_member.id, "order_id": 99999, "points": 10,
    })
    assert resp.status_code == 404


def test_redeem_member_mismatch_returns_400(app, client, logged_in_staff, seeded_member):
    from app.services import auth_service, member_service, order_service
    other = member_service.create_member(name="Other", phone_number="5550000001")
    order = order_service.create_order(member_id=other.id, subtotal=100.0)
    resp = client.post("/api/points/redeem", json={
        "member_id": seeded_member.id,
        "order_id": order.id,
        "points": 5,
    })
    assert resp.status_code == 400
    assert "belong" in resp.get_json()["error"]


def test_redeem_wrong_state_returns_400(app, client, logged_in_staff, seeded_member):
    from app.services import order_service
    from app.db import db
    order = order_service.create_order(member_id=seeded_member.id, subtotal=50.0)
    order.status = "fulfilled"
    db.session.commit()
    resp = client.post("/api/points/redeem", json={
        "member_id": seeded_member.id, "order_id": order.id, "points": 5,
    })
    assert resp.status_code == 400


def test_points_balance_endpoint(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/points/balance/{seeded_member.id}")
    assert resp.status_code == 200
    assert "balance" in resp.get_json()


def test_points_history_endpoint(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/points/history/{seeded_member.id}")
    assert resp.status_code == 200
    assert "results" in resp.get_json()


def test_daily_redemption_limit_triggers_flag(
    app, client, logged_in_staff, seeded_member
):
    """Over 10 redemptions in a single day should trigger a risk flag."""
    # Earn a large number of points
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 5000.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})

    member = db.session.get(Member, seeded_member.id)
    assert member.points_balance == 5000

    # Make 11 small redemptions (each within 20% cap)
    for i in range(11):
        # Create a new order each time with subtotal=100 (20% = 20 max)
        resp = client.post(
            "/api/orders",
            json={"member_id": seeded_member.id, "subtotal": 100.0},
        )
        oid = resp.get_json()["id"]
        points_service.redeem_points(
            member_id=seeded_member.id,
            order_id=oid,
            points_to_redeem=5,
            order_subtotal=100.0,
        )

    # After 11 redemptions, member should be flagged
    assert risk_service.has_active_member_flag(seeded_member.id, "points_abuse")
