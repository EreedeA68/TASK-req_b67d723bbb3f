"""Order service — creation and lifecycle. All state-machine enforcement
lives here, not in routes."""
from app.core.state_machine import (
    FINAL_STATES,
    InvalidTransitionError,
    next_status,
    validate_transition,
)
from app.db import db
from app.models.member import Member
from app.models.order import Order, OrderEvent
from app.services import audit_service


class OrderError(Exception):
    """Error in order operations."""


class OrderAccessDenied(OrderError):
    """Object-level access denied."""


def check_access(order: Order, actor_id: int | None) -> None:
    """Enforce object-level ownership on orders.

    Operational roles (admin, staff, kitchen) may access any order because
    cross-user order processing is a core workflow.  Other roles are
    restricted to orders they created.

    Raises OrderAccessDenied if the actor lacks access.
    Must be called from both API and view layers before mutations/reads.
    """
    if order is None or actor_id is None:
        raise OrderAccessDenied("forbidden")
    from app.db import db as _db
    from app.models.user import User

    actor = _db.session.get(User, actor_id)
    if actor is None:
        raise OrderAccessDenied("forbidden")
    # Operational roles need cross-order access for normal workflow.
    if actor.has_role("admin") or actor.has_role("staff") or actor.has_role("kitchen"):
        return
    # All other roles: restricted to orders they created.
    if order.created_by is not None and order.created_by != actor_id:
        raise OrderAccessDenied("forbidden")


def _validate_amount(value, name: str) -> float:
    if value is None:
        raise OrderError(f"{name} is required")
    try:
        val = float(value)
    except (TypeError, ValueError) as exc:
        raise OrderError(f"{name} must be numeric") from exc
    if val < 0:
        raise OrderError(f"{name} must be >= 0")
    return val


def create_order(
    member_id: int,
    subtotal: float,
    *,
    discount: float = 0.0,
    items: list[dict] | None = None,
    actor_id: int | None = None,
) -> Order:
    if member_id is None:
        raise OrderError("member_id is required")
    subtotal_f = _validate_amount(subtotal, "subtotal")
    discount_f = _validate_amount(discount or 0.0, "discount")
    if discount_f > subtotal_f:
        raise OrderError("discount must not exceed subtotal")

    member = db.session.get(Member, member_id)
    if member is None:
        raise OrderError("member not found")

    # Enforce tier-based discount cap
    from app.models.tier_rule import TierRule

    tier_rule = TierRule.query.filter_by(tier_name=member.tier).first()
    if tier_rule is not None:
        max_discount = subtotal_f * tier_rule.max_discount_pct
        if discount_f > max_discount:
            raise OrderError(
                f"discount ${discount_f:.2f} exceeds tier '{member.tier}' "
                f"max of {tier_rule.max_discount_pct * 100:.0f}% "
                f"(${max_discount:.2f})"
            )
    else:
        # No rule found — default to 0 discount allowed
        if discount_f > 0:
            raise OrderError(
                f"no discount rule found for tier '{member.tier}'; "
                f"discount not allowed"
            )

    total = max(0.0, subtotal_f - discount_f)
    order = Order(
        member_id=member.id,
        created_by=actor_id,
        status="created",
        subtotal=subtotal_f,
        discount=discount_f,
        total=total,
    )
    db.session.add(order)
    db.session.flush()

    # Create OrderItem records if items provided
    if items:
        from app.models.order_item import OrderItem

        for item_data in items:
            order_item = OrderItem(
                order_id=order.id,
                name=item_data.get("name", ""),
                category=item_data.get("category", ""),
                quantity=item_data.get("quantity", 1),
                unit_price=item_data.get("unit_price", 0.0),
                allergy_note=item_data.get("allergy_note"),
            )
            db.session.add(order_item)

    event = OrderEvent(order_id=order.id, status="created", actor_id=actor_id)
    db.session.add(event)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="order_created",
        resource=f"order:{order.id}",
        metadata={"member_id": member.id, "total": total},
    )
    return order


def get_by_id(order_id: int, *, check_expiry: bool = True) -> Order | None:
    order = db.session.get(Order, order_id)
    if order is not None and check_expiry:
        from app.services.expiry_service import check_order_expiry

        order = check_order_expiry(order)
    return order


def transition(order: Order, target: str, *, actor_id: int | None = None) -> Order:
    """Enforce strict state-machine transitions.

    Rejects:
      * invalid transitions
      * duplicate transitions (target == current)
      * transitions out of a final state
    Every rejection is audited.
    """
    if order is None:
        raise OrderError("order is required")
    current = order.status

    # Duplicate / no-op transitions — rejected and audited.
    if target == current:
        audit_service.log(
            actor_id=actor_id,
            action="order_transition_rejected",
            resource=f"order:{order.id}",
            metadata={
                "from": current,
                "to": target,
                "reason": "duplicate",
            },
        )
        raise OrderError(
            f"duplicate transition: order is already in '{current}'"
        )

    # Transitions from a final state.
    if current in FINAL_STATES:
        audit_service.log(
            actor_id=actor_id,
            action="order_transition_rejected",
            resource=f"order:{order.id}",
            metadata={
                "from": current,
                "to": target,
                "reason": "final_state",
            },
        )
        raise OrderError(
            f"order is in final state '{current}'; no further transitions allowed"
        )

    try:
        validate_transition(current, target)
    except InvalidTransitionError as exc:
        audit_service.log(
            actor_id=actor_id,
            action="order_transition_rejected",
            resource=f"order:{order.id}",
            metadata={
                "from": current,
                "to": target,
                "reason": "invalid",
            },
        )
        raise OrderError(str(exc)) from exc

    order.status = target
    db.session.add(
        OrderEvent(order_id=order.id, status=target, actor_id=actor_id)
    )
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="order_status_change",
        resource=f"order:{order.id}",
        metadata={"from": current, "to": target},
    )

    # Auto-generate KDS tickets when order enters prep
    if target == "in_prep":
        from app.services import kds_service
        try:
            items = order.items if hasattr(order, 'items') else []
            if items:
                stations_set = set()
                has_allergy = False
                for item in items:
                    stations_set.add(kds_service.map_station(item.category))
                    if item.allergy_note:
                        has_allergy = True
                kds_service.generate_tickets(
                    order, stations=list(stations_set), allergy_flag=has_allergy, actor_id=actor_id
                )
            else:
                kds_service.generate_tickets(order, actor_id=actor_id)
        except kds_service.KDSError:
            pass  # KDS failure must not block order transition

    return order


def pay(order: Order, *, redeem_points: int = 0, actor_id: int | None = None) -> Order:
    """Transition an order from created -> paid, then award loyalty points.

    If *redeem_points* > 0, redeems that many points (1 point = $1) and
    generates a Receipt record capturing the full checkout breakdown.
    """
    from app.services import points_service

    order = transition(order, "paid", actor_id=actor_id)

    # Handle points redemption if requested
    points_value = 0.0
    points_redeemed = 0
    redeem_error = None
    if redeem_points and redeem_points > 0:
        try:
            points_service.redeem_points(
                member_id=order.member_id,
                order_id=order.id,
                points_to_redeem=redeem_points,
                order_subtotal=order.subtotal,
                actor_id=actor_id,
            )
            points_redeemed = redeem_points
            points_value = float(redeem_points)  # 1 point = $1
        except points_service.PointsError as exc:
            redeem_error = str(exc)
            audit_service.log(
                actor_id=actor_id,
                action="points_redeem_failed",
                resource=f"order:{order.id}",
                metadata={"error": redeem_error, "points_requested": redeem_points},
            )

    # Award points: 1 point per $1.00 pre-tax (based on subtotal)
    points_earned = 0
    earn_error = None
    try:
        entry = points_service.earn_points(
            member_id=order.member_id,
            order_id=order.id,
            subtotal=order.subtotal,
            actor_id=actor_id,
        )
        points_earned = entry.points
    except points_service.PointsError as exc:
        earn_error = str(exc)

    # Generate receipt — note includes redemption failure if applicable
    from app.models.receipt import Receipt

    note_parts = []
    if points_redeemed > 0:
        note_parts.append(f"Points redeemed: {points_redeemed}")
    if redeem_error:
        note_parts.append(f"Redemption failed: {redeem_error}")

    final_total = max(0.0, order.total - points_value)
    receipt = Receipt(
        order_id=order.id,
        member_id=order.member_id,
        subtotal=order.subtotal,
        discount=order.discount,
        points_redeemed=points_redeemed,
        points_value=points_value,
        total=final_total,
        points_earned=points_earned,
        note="; ".join(note_parts) if note_parts else None,
    )
    db.session.add(receipt)
    db.session.commit()

    # Attach redemption outcome to order for caller visibility
    order._redeem_error = redeem_error

    return order


def advance(order: Order, *, actor_id: int | None = None) -> Order:
    """Advance an order to the next state in the machine."""
    if order is None:
        raise OrderError("order is required")
    if order.status in FINAL_STATES:
        audit_service.log(
            actor_id=actor_id,
            action="order_transition_rejected",
            resource=f"order:{order.id}",
            metadata={
                "from": order.status,
                "to": None,
                "reason": "final_state",
            },
        )
        raise OrderError(
            f"order is in final state '{order.status}'; cannot advance"
        )
    try:
        target = next_status(order.status)
    except InvalidTransitionError as exc:
        raise OrderError(str(exc)) from exc
    return transition(order, target, actor_id=actor_id)
