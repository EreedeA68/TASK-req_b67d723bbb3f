"""Tier-based discount governance tests."""
import pytest

from app.services import order_service
from app.services.order_service import OrderError


def test_standard_member_max_5_percent(app, seeded_member, staff_user):
    """Standard tier member can get up to 5% discount."""
    # seeded_member has tier="standard" by default
    assert seeded_member.tier == "standard"

    # 5% of 100 = 5.0 — should succeed
    order = order_service.create_order(
        member_id=seeded_member.id,
        subtotal=100.0,
        discount=5.0,
        actor_id=staff_user.id,
    )
    assert order.discount == 5.0
    assert order.total == 95.0


def test_standard_member_exceeds_5_percent_rejected(app, seeded_member, staff_user):
    """Standard tier member cannot get more than 5% discount."""
    assert seeded_member.tier == "standard"

    # 6% of 100 = 6.0 — should be rejected
    with pytest.raises(OrderError, match="discount"):
        order_service.create_order(
            member_id=seeded_member.id,
            subtotal=100.0,
            discount=6.0,
            actor_id=staff_user.id,
        )


def test_gold_member_up_to_15_percent(app, staff_user):
    """Gold tier member can get up to 15% discount."""
    from app.services import member_service

    gold_member = member_service.create_member(
        name="Gold User",
        phone_number="5559990001",
        member_id="M-GOLD0001",
        tier="gold",
        actor_id=staff_user.id,
    )
    assert gold_member.tier == "gold"

    # 15% of 200 = 30.0 — should succeed
    order = order_service.create_order(
        member_id=gold_member.id,
        subtotal=200.0,
        discount=30.0,
        actor_id=staff_user.id,
    )
    assert order.discount == 30.0
    assert order.total == 170.0


def test_gold_member_exceeds_15_percent_rejected(app, staff_user):
    """Gold tier member cannot exceed 15% discount."""
    from app.services import member_service

    gold_member = member_service.create_member(
        name="Gold User 2",
        phone_number="5559990002",
        member_id="M-GOLD0002",
        tier="gold",
        actor_id=staff_user.id,
    )

    # 16% of 200 = 32.0 — should be rejected
    with pytest.raises(OrderError, match="discount"):
        order_service.create_order(
            member_id=gold_member.id,
            subtotal=200.0,
            discount=32.0,
            actor_id=staff_user.id,
        )


def test_silver_member_up_to_10_percent(app, staff_user):
    """Silver tier member can get up to 10% discount."""
    from app.services import member_service

    silver_member = member_service.create_member(
        name="Silver User",
        phone_number="5559990003",
        member_id="M-SILVER001",
        tier="silver",
        actor_id=staff_user.id,
    )

    # 10% of 100 = 10.0 — should succeed
    order = order_service.create_order(
        member_id=silver_member.id,
        subtotal=100.0,
        discount=10.0,
        actor_id=staff_user.id,
    )
    assert order.discount == 10.0
    assert order.total == 90.0


def test_platinum_member_up_to_20_percent(app, staff_user):
    """Platinum tier member can get up to 20% discount."""
    from app.services import member_service

    plat_member = member_service.create_member(
        name="Platinum User",
        phone_number="5559990004",
        member_id="M-PLAT0001",
        tier="platinum",
        actor_id=staff_user.id,
    )

    # 20% of 100 = 20.0 — should succeed
    order = order_service.create_order(
        member_id=plat_member.id,
        subtotal=100.0,
        discount=20.0,
        actor_id=staff_user.id,
    )
    assert order.discount == 20.0
    assert order.total == 80.0


def test_zero_discount_always_ok(app, seeded_member, staff_user):
    """Zero discount should always be allowed regardless of tier."""
    order = order_service.create_order(
        member_id=seeded_member.id,
        subtotal=100.0,
        discount=0.0,
        actor_id=staff_user.id,
    )
    assert order.discount == 0.0
    assert order.total == 100.0


def test_unknown_tier_no_discount(app, staff_user):
    """Unknown tier with no rule defaults to 0 discount allowed."""
    from app.db import db
    from app.models.member import Member
    from app.core.encryption import encrypt

    member = Member(
        name="Unknown Tier",
        phone_number=encrypt("5559990099"),
        member_id="M-UNK0001",
        tier="unknown_tier",
        stored_value_balance=encrypt("0"),
    )
    db.session.add(member)
    db.session.commit()

    # Any discount should be rejected
    with pytest.raises(OrderError, match="no discount rule found"):
        order_service.create_order(
            member_id=member.id,
            subtotal=100.0,
            discount=1.0,
            actor_id=staff_user.id,
        )

    # Zero discount should work
    order = order_service.create_order(
        member_id=member.id,
        subtotal=100.0,
        discount=0.0,
        actor_id=staff_user.id,
    )
    assert order.total == 100.0


def test_tier_rules_seeded(app):
    """Verify default tier rules are seeded at app startup."""
    from app.models.tier_rule import TierRule

    standard = TierRule.query.filter_by(tier_name="standard").first()
    assert standard is not None
    assert standard.max_discount_pct == 0.05

    gold = TierRule.query.filter_by(tier_name="gold").first()
    assert gold is not None
    assert gold.max_discount_pct == 0.15

    platinum = TierRule.query.filter_by(tier_name="platinum").first()
    assert platinum is not None
    assert platinum.max_discount_pct == 0.20
