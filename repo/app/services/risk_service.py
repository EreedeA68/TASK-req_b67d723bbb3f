"""Fraud / risk control service."""
from datetime import datetime, timedelta

from app.db import db
from app.models.risk import RiskFlag
from app.services import audit_service


class RiskError(Exception):
    """Error in risk operations."""


POINTS_DAILY_LIMIT = 10
SPEND_DAILY_LIMIT = 200.0


def check_points_abuse(user_id: int, redemptions_today: int) -> bool:
    """Return True if user exceeds daily points redemption limit."""
    return redemptions_today > POINTS_DAILY_LIMIT


def check_spend_abuse(user_id: int, spend_today: float) -> bool:
    """Return True if user exceeds daily stored-value spend limit."""
    return spend_today > SPEND_DAILY_LIMIT


def flag_user(
    user_id: int,
    flag_type: str,
    *,
    actor_id: int | None = None,
) -> RiskFlag:
    """Create a risk flag for a user (idempotent — won't duplicate active flags)."""
    if flag_type not in ("points_abuse", "spend_abuse"):
        raise RiskError(f"invalid flag type: {flag_type}")

    existing = RiskFlag.query.filter_by(
        user_id=user_id, type=flag_type, active=True
    ).first()
    if existing:
        return existing  # Already flagged

    flag = RiskFlag(user_id=user_id, type=flag_type, active=True)
    db.session.add(flag)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="risk_flag_triggered",
        resource=f"user:{user_id}",
        metadata={"type": flag_type},
    )
    return flag


def flag_member(
    member_id: int,
    flag_type: str,
    *,
    actor_id: int | None = None,
) -> RiskFlag:
    """Create a risk flag for a member (idempotent — won't duplicate active flags)."""
    if flag_type not in ("points_abuse", "spend_abuse"):
        raise RiskError(f"invalid flag type: {flag_type}")

    existing = RiskFlag.query.filter_by(
        member_id=member_id, type=flag_type, active=True
    ).first()
    if existing:
        return existing  # Already flagged

    flag = RiskFlag(member_id=member_id, type=flag_type, active=True)
    db.session.add(flag)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="risk_flag_triggered",
        resource=f"member:{member_id}",
        metadata={"type": flag_type},
    )
    return flag


def clear_flags(
    user_id: int,
    *,
    actor_id: int | None = None,
) -> int:
    """Clear all active risk flags for a user. Returns count cleared."""
    flags = RiskFlag.query.filter_by(user_id=user_id, active=True).all()
    count = 0
    for f in flags:
        f.active = False
        count += 1
    db.session.commit()

    if count:
        audit_service.log(
            actor_id=actor_id,
            action="risk_flag_cleared",
            resource=f"user:{user_id}",
            metadata={"cleared": count},
        )
    return count


def clear_member_flags(
    member_id: int,
    *,
    actor_id: int | None = None,
) -> int:
    """Clear all active risk flags for a member. Returns count cleared."""
    flags = RiskFlag.query.filter_by(member_id=member_id, active=True).all()
    count = 0
    for f in flags:
        f.active = False
        count += 1
    db.session.commit()

    if count:
        audit_service.log(
            actor_id=actor_id,
            action="risk_flag_cleared",
            resource=f"member:{member_id}",
            metadata={"cleared": count},
        )
    return count


def has_active_flag(user_id: int, flag_type: str | None = None) -> bool:
    """Check if a user has any (or a specific type of) active risk flag."""
    query = RiskFlag.query.filter_by(user_id=user_id, active=True)
    if flag_type:
        query = query.filter_by(type=flag_type)
    return query.first() is not None


def has_active_member_flag(member_id: int, flag_type: str | None = None) -> bool:
    """Check if a member has any (or a specific type of) active risk flag."""
    query = RiskFlag.query.filter_by(member_id=member_id, active=True)
    if flag_type:
        query = query.filter_by(type=flag_type)
    return query.first() is not None


def list_flags(*, active_only: bool = True) -> list[RiskFlag]:
    query = RiskFlag.query
    if active_only:
        query = query.filter_by(active=True)
    return query.order_by(RiskFlag.created_at.desc()).all()
