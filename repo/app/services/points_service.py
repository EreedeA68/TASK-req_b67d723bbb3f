"""Points economy service — earn, redeem, expire, and balance queries."""
import math
from datetime import datetime, timedelta

from app.db import db
from app.models.member import Member
from app.models.points import POINTS_EXPIRY_DAYS, PointLedger
from app.services import audit_service
from app.services import risk_service

# Redemption cap: maximum percentage of order subtotal redeemable via points
REDEMPTION_CAP_PCT = 0.20

# Daily abuse thresholds (mirrors risk_service constants)
DAILY_REDEMPTION_LIMIT = 10
DAILY_SPEND_LIMIT = 200.0


class PointsError(Exception):
    """Error in points operations."""


def earn_points(
    member_id: int,
    order_id: int,
    subtotal: float,
    actor_id: int | None = None,
) -> PointLedger:
    """Award floor(subtotal) points to a member for a paid order.

    Points earn at 1 point per $1.00 pre-tax (based on subtotal).
    Earn entries expire 365 days after issuance.
    """
    member = db.session.get(Member, member_id)
    if member is None:
        raise PointsError("member not found")

    points = int(math.floor(subtotal))
    if points <= 0:
        raise PointsError("no points to award for this subtotal")

    now = datetime.utcnow()
    entry = PointLedger(
        member_id=member.id,
        type="earn",
        points=points,
        order_id=order_id,
        created_at=now,
        expires_at=now + timedelta(days=POINTS_EXPIRY_DAYS),
    )
    db.session.add(entry)

    member.points_balance += points
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="points_earned",
        resource=f"member:{member.id}",
        metadata={
            "points": points,
            "order_id": order_id,
            "subtotal": subtotal,
        },
    )
    return entry


def redeem_points(
    member_id: int,
    order_id: int,
    points_to_redeem: int,
    order_subtotal: float,
    actor_id: int | None = None,
) -> PointLedger:
    """Redeem points against an order.

    Validates:
    - Sufficient balance (excluding expired)
    - 20% cap on order subtotal
    - No active risk flags on the member
    Creates a redeem ledger entry and updates member.points_balance.
    After redemption, checks daily abuse thresholds.
    """
    if points_to_redeem <= 0:
        raise PointsError("points_to_redeem must be positive")

    member = db.session.get(Member, member_id)
    if member is None:
        raise PointsError("member not found")

    # Check risk flag before allowing redemption.  The prompt treats any
    # active high-risk flag (points_abuse or spend_abuse) as blocking until
    # an admin clears it.
    for flag_type in ("points_abuse", "spend_abuse"):
        if risk_service.has_active_member_flag(member.id, flag_type):
            raise PointsError(
                f"redemption blocked by active risk flag: {flag_type}"
            )

    # Expire any stale points first
    expire_points(member_id)

    # Re-read member after expiry adjustment
    member = db.session.get(Member, member_id)

    # Check balance
    balance = get_balance(member_id)
    if points_to_redeem > balance:
        raise PointsError("insufficient points balance")

    # Check 20% cap
    max_redeemable = int(math.floor(order_subtotal * REDEMPTION_CAP_PCT))
    if points_to_redeem > max_redeemable:
        raise PointsError(
            f"redemption exceeds 20% cap: max {max_redeemable} points "
            f"for subtotal {order_subtotal}"
        )

    # Create redeem entry (no expiry for redeems)
    entry = PointLedger(
        member_id=member.id,
        type="redeem",
        points=points_to_redeem,
        order_id=order_id,
        created_at=datetime.utcnow(),
        expires_at=None,
    )
    db.session.add(entry)

    member.points_balance -= points_to_redeem
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="points_redeemed",
        resource=f"member:{member.id}",
        metadata={
            "points": points_to_redeem,
            "order_id": order_id,
            "order_subtotal": order_subtotal,
        },
    )

    # Post-redemption abuse check
    _check_daily_abuse(member.id, actor_id=actor_id)

    return entry


def get_balance(member_id: int) -> int:
    """Return the current effective points balance, excluding expired earn entries.

    Computes: sum(earn entries not expired) - sum(redeem entries).
    """
    now = datetime.utcnow()

    # Sum of non-expired earn entries
    earned = (
        db.session.query(db.func.coalesce(db.func.sum(PointLedger.points), 0))
        .filter(
            PointLedger.member_id == member_id,
            PointLedger.type == "earn",
            db.or_(
                PointLedger.expires_at.is_(None),
                PointLedger.expires_at > now,
            ),
        )
        .scalar()
    )

    # Sum of all redeem entries
    redeemed = (
        db.session.query(db.func.coalesce(db.func.sum(PointLedger.points), 0))
        .filter(
            PointLedger.member_id == member_id,
            PointLedger.type == "redeem",
        )
        .scalar()
    )

    return int(earned) - int(redeemed)


def expire_points(member_id: int) -> int:
    """Expire any earn ledger entries past their expires_at.

    Adjusts member.points_balance by the total expired amount.
    Returns the number of points expired.
    """
    now = datetime.utcnow()
    expired_entries = PointLedger.query.filter(
        PointLedger.member_id == member_id,
        PointLedger.type == "earn",
        PointLedger.expires_at.isnot(None),
        PointLedger.expires_at <= now,
    ).all()

    if not expired_entries:
        return 0

    total_expired = sum(e.points for e in expired_entries)

    # Remove expired entries from the ledger (or mark them — here we delete
    # them so they don't count in balance calculations, and record an audit).
    for e in expired_entries:
        db.session.delete(e)

    member = db.session.get(Member, member_id)
    if member is not None:
        member.points_balance = max(0, member.points_balance - total_expired)

    db.session.commit()

    audit_service.log(
        actor_id=None,
        action="points_expired",
        resource=f"member:{member_id}",
        metadata={"points_expired": total_expired},
    )
    return total_expired


def get_history(member_id: int) -> list[PointLedger]:
    """Return all ledger entries for a member, newest first."""
    return (
        PointLedger.query.filter_by(member_id=member_id)
        .order_by(PointLedger.created_at.desc())
        .all()
    )


def _check_daily_abuse(member_id: int, *, actor_id: int | None = None) -> None:
    """Check if the member has exceeded daily redemption thresholds.

    Triggers a risk flag if:
    - Over 10 redemptions today, OR
    - Over $200 worth of points redeemed today
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    today_redemptions = PointLedger.query.filter(
        PointLedger.member_id == member_id,
        PointLedger.type == "redeem",
        PointLedger.created_at >= today_start,
    ).all()

    redemption_count = len(today_redemptions)
    redemption_total = sum(e.points for e in today_redemptions)

    if risk_service.check_points_abuse(member_id, redemption_count):
        risk_service.flag_member(
            member_id, "points_abuse", actor_id=actor_id
        )

    if risk_service.check_spend_abuse(member_id, float(redemption_total)):
        risk_service.flag_member(
            member_id, "points_abuse", actor_id=actor_id
        )
