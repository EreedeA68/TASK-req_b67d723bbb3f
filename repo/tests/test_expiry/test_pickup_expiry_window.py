"""Test the prompt-aligned single-4h pickup expiry window.

Per prompt: paid-but-unclaimed orders move to 'ready_for_pickup' and expire
after 4 hours for end-of-day reconciliation — a single 4-hour deadline.
"""
from datetime import datetime, timedelta

from app.db import db
from app.models.order import OrderEvent
from app.services.expiry_service import check_order_expiry


def _create_paid_ready_order(app, member_id, staff_id):
    from app.services import order_service
    order = order_service.create_order(
        member_id=member_id, subtotal=50.0, actor_id=staff_id,
    )
    order_service.pay(order, actor_id=staff_id)
    order_service.transition(order, "in_prep", actor_id=staff_id)
    order_service.transition(order, "ready", actor_id=staff_id)
    return order


def test_ready_for_pickup_cancels_at_single_4h_deadline(
    app, logged_in_staff, seeded_member, staff_user
):
    """After the 4-hour window from ready, order is cancelled (via
    ready_for_pickup intermediate state for reconciliation labeling)."""
    order = _create_paid_ready_order(app, seeded_member.id, staff_user.id)

    # Backdate ready event past the 4-hour deadline
    ready_event = OrderEvent.query.filter_by(
        order_id=order.id, status="ready"
    ).first()
    ready_event.timestamp = datetime.utcnow() - timedelta(hours=5)
    db.session.commit()

    # Trigger lazy expiry — moves to ready_for_pickup
    order = check_order_expiry(order)
    assert order.status == "ready_for_pickup"

    # Re-check immediately — the single 4h deadline has already passed, so
    # the pickup state should cancel on the next check (no extended window).
    order = check_order_expiry(order)
    assert order.status == "cancelled"


def test_ready_order_within_4h_is_not_expired(
    app, logged_in_staff, seeded_member, staff_user
):
    """Orders in ready state within the 4h window are not touched."""
    order = _create_paid_ready_order(app, seeded_member.id, staff_user.id)

    # ready was just set — nothing should happen
    order = check_order_expiry(order)
    assert order.status == "ready"
