"""Tests for autonomous expiry processing (independent of order fetch)."""
from datetime import datetime, timedelta

from app.db import db
from app.models.order import Order, OrderEvent
from app.services.expiry_service import process_all_expired_orders


def _create_order(app, member_id, staff_id):
    """Create an order directly via service layer."""
    from app.services import order_service
    return order_service.create_order(
        member_id=member_id, subtotal=50.0, actor_id=staff_id,
    )


def test_sweep_cancels_unpaid_orders(app, logged_in_staff, seeded_member, staff_user):
    """process_all_expired_orders cancels stale unpaid orders without a fetch."""
    order = _create_order(app, seeded_member.id, staff_user.id)
    assert order.status == "created"

    # Backdate creation to 31 minutes ago
    order.created_at = datetime.utcnow() - timedelta(minutes=31)
    db.session.commit()

    # Run autonomous sweep (NOT fetching the order first)
    result = process_all_expired_orders()
    assert result["cancelled"] >= 1

    # Verify order was cancelled
    db.session.expire_all()
    updated = db.session.get(Order, order.id)
    assert updated.status == "cancelled"


def test_sweep_moves_ready_to_pickup(app, logged_in_staff, seeded_member, staff_user):
    """process_all_expired_orders moves stale ready orders to ready_for_pickup."""
    from app.services import order_service

    order = _create_order(app, seeded_member.id, staff_user.id)
    order_service.pay(order, actor_id=staff_user.id)
    order_service.transition(order, "in_prep", actor_id=staff_user.id)
    order_service.transition(order, "ready", actor_id=staff_user.id)
    assert order.status == "ready"

    # Backdate the ready event to 5 hours ago
    ready_event = OrderEvent.query.filter_by(
        order_id=order.id, status="ready"
    ).first()
    ready_event.timestamp = datetime.utcnow() - timedelta(hours=5)
    db.session.commit()

    result = process_all_expired_orders()
    assert result["moved_to_pickup"] >= 1

    db.session.expire_all()
    updated = db.session.get(Order, order.id)
    assert updated.status == "ready_for_pickup"


def test_sweep_skips_active_orders(app, logged_in_staff, seeded_member, staff_user):
    """Orders within their time window should not be affected by the sweep."""
    order = _create_order(app, seeded_member.id, staff_user.id)
    assert order.status == "created"
    # Order was just created — should NOT be expired

    result = process_all_expired_orders()
    assert result["cancelled"] == 0
    assert result["moved_to_pickup"] == 0

    db.session.expire_all()
    updated = db.session.get(Order, order.id)
    assert updated.status == "created"
