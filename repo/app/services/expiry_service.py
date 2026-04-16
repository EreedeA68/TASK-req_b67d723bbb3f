"""Order and booking expiry — lazy on fetch + autonomous periodic sweep."""
import threading
from datetime import datetime, timedelta

from app.db import db
from app.models.order import Order, OrderEvent
from app.services import audit_service

# Unpaid orders expire after 30 minutes.
UNPAID_EXPIRY_MINUTES = 30
# Paid-but-unclaimed orders move to "ready_for_pickup" and expire after 4 hours.
# Single 4-hour deadline matches the prompt's paid-unclaimed expiry rule: once
# the 4-hour window from "ready" passes, the order is cancelled (transitioning
# through ready_for_pickup for reconciliation labeling).
READY_EXPIRY_MINUTES = 240
# Pickup-window after moving to ready_for_pickup is 0 — cancellation is
# effectively immediate once the single 4-hour deadline has passed.
PICKUP_EXPIRY_MINUTES = 0


def _last_event_time(order: Order, status: str) -> datetime | None:
    """Return the timestamp of the most recent event with the given status."""
    event = (
        OrderEvent.query
        .filter_by(order_id=order.id, status=status)
        .order_by(OrderEvent.timestamp.desc())
        .first()
    )
    return event.timestamp if event else None


def check_order_expiry(order: Order) -> Order:
    """Expire an order if its time window has passed.

    Called lazily on fetch/action.  Mutates and commits if expired.
    - Unpaid (created) orders: cancel after 30 minutes from creation.
    - Ready orders: move to ready_for_pickup after 4 hours from reaching "ready".
    - Ready-for-pickup orders: cancel for end-of-day reconciliation.
    """
    if order is None:
        return order

    now = datetime.utcnow()

    if order.status == "created":
        cutoff = order.created_at + timedelta(minutes=UNPAID_EXPIRY_MINUTES)
        if now >= cutoff:
            return _expire_order(order, reason="unpaid_timeout")

    if order.status == "ready":
        # After 4h unclaimed, transition to ready_for_pickup.
        ready_at = _last_event_time(order, "ready") or order.created_at
        cutoff = ready_at + timedelta(minutes=READY_EXPIRY_MINUTES)
        if now >= cutoff:
            return _transition_to_pickup(order)

    if order.status == "ready_for_pickup":
        # Distinct pickup window: cancel after PICKUP_EXPIRY_MINUTES from
        # entering ready_for_pickup (not from the original "ready" time).
        pickup_at = _last_event_time(order, "ready_for_pickup") or order.created_at
        cutoff = pickup_at + timedelta(minutes=PICKUP_EXPIRY_MINUTES)
        if now >= cutoff:
            return _expire_order(order, reason="pickup_expired")

    return order


def _transition_to_pickup(order: Order) -> Order:
    """Move an unclaimed ready order to ready_for_pickup."""
    prev = order.status
    order.status = "ready_for_pickup"
    db.session.add(
        OrderEvent(order_id=order.id, status="ready_for_pickup", actor_id=None)
    )
    db.session.commit()

    audit_service.log(
        actor_id=None,
        action="order_ready_for_pickup",
        resource=f"order:{order.id}",
        metadata={"from": prev},
    )
    return order


def _expire_order(order: Order, *, reason: str) -> Order:
    prev = order.status
    order.status = "cancelled"
    db.session.add(
        OrderEvent(order_id=order.id, status="cancelled", actor_id=None)
    )
    db.session.commit()

    audit_service.log(
        actor_id=None,
        action="order_expired",
        resource=f"order:{order.id}",
        metadata={"from": prev, "reason": reason},
    )
    return order


# --------------- Autonomous periodic sweep ---------------

def process_all_expired_orders() -> dict:
    """Scan all orders in expirable states and apply expiry transitions.

    Unlike check_order_expiry (which runs lazily on fetch), this function
    processes all eligible orders in a single sweep.  Suitable for a CLI
    command, background timer, or cron job.

    Returns a summary dict with counts of transitions made.
    """
    now = datetime.utcnow()
    cancelled = 0
    moved_to_pickup = 0

    # Unpaid orders past 30-minute window
    unpaid_cutoff = now - timedelta(minutes=UNPAID_EXPIRY_MINUTES)
    stale_unpaid = Order.query.filter(
        Order.status == "created",
        Order.created_at <= unpaid_cutoff,
    ).all()
    for order in stale_unpaid:
        _expire_order(order, reason="unpaid_timeout")
        cancelled += 1

    # Ready orders past 4-hour window → ready_for_pickup
    just_moved_ids: set[int] = set()
    ready_orders = Order.query.filter(Order.status == "ready").all()
    for order in ready_orders:
        ready_at = _last_event_time(order, "ready") or order.created_at
        cutoff = ready_at + timedelta(minutes=READY_EXPIRY_MINUTES)
        if now >= cutoff:
            _transition_to_pickup(order)
            just_moved_ids.add(order.id)
            moved_to_pickup += 1

    # Ready-for-pickup orders → cancel after distinct pickup window
    pickup_orders = Order.query.filter(Order.status == "ready_for_pickup").all()
    for order in pickup_orders:
        if order.id in just_moved_ids:
            continue
        pickup_at = _last_event_time(order, "ready_for_pickup") or order.created_at
        cutoff = pickup_at + timedelta(minutes=PICKUP_EXPIRY_MINUTES)
        if now >= cutoff:
            _expire_order(order, reason="pickup_expired")
            cancelled += 1

    return {
        "cancelled": cancelled,
        "moved_to_pickup": moved_to_pickup,
    }


# --------------- Background ticker ---------------

_expiry_timer: threading.Timer | None = None
EXPIRY_INTERVAL_SECONDS = 60  # check every 60 seconds


def start_expiry_ticker(app) -> None:
    """Start a background thread that runs expiry sweeps periodically.

    Safe for single-process deployments (the typical offline use case).
    The ticker runs inside an app context and respects TESTING mode.
    """
    if app.config.get("TESTING"):
        return  # never auto-start in tests

    def _tick():
        global _expiry_timer
        with app.app_context():
            try:
                process_all_expired_orders()
            except Exception:
                pass  # ticker must not crash the app
        _expiry_timer = threading.Timer(EXPIRY_INTERVAL_SECONDS, _tick)
        _expiry_timer.daemon = True
        _expiry_timer.start()

    _tick()


def stop_expiry_ticker() -> None:
    """Cancel the background expiry timer."""
    global _expiry_timer
    if _expiry_timer is not None:
        _expiry_timer.cancel()
        _expiry_timer = None
