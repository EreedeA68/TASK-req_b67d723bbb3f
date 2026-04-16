"""Stored-value service — credit, debit, balance, and history."""
from datetime import datetime

from app.core.encryption import decrypt, encrypt
from app.db import db
from app.models.member import Member
from app.models.stored_value import StoredValueLedger
from app.services import audit_service
from app.services import risk_service


DAILY_SPEND_LIMIT = 200.0


class StoredValueError(Exception):
    """Error in stored-value operations."""


def _get_encrypted_balance(member: Member) -> float:
    """Decrypt and return the member's current stored-value balance."""
    raw = member.stored_value_balance or "0"
    decrypted = decrypt(raw)
    if not decrypted:
        decrypted = raw
    try:
        return float(decrypted)
    except (TypeError, ValueError):
        return 0.0


def _set_encrypted_balance(member: Member, balance: float) -> None:
    """Encrypt and set the member's stored-value balance."""
    member.stored_value_balance = encrypt(str(balance))


def credit(
    member_id: int,
    amount: float,
    description: str | None = None,
    order_id: int | None = None,
    actor_id: int | None = None,
) -> StoredValueLedger:
    """Add a credit entry and update member's encrypted stored_value_balance."""
    if amount is None or amount <= 0:
        raise StoredValueError("amount must be positive")

    member = db.session.get(Member, member_id)
    if member is None:
        raise StoredValueError("member not found")

    entry = StoredValueLedger(
        member_id=member.id,
        type="credit",
        amount=amount,
        order_id=order_id,
        description=description,
        created_at=datetime.utcnow(),
    )
    db.session.add(entry)

    current_balance = _get_encrypted_balance(member)
    _set_encrypted_balance(member, current_balance + amount)

    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="stored_value_credit",
        resource=f"member:{member.id}",
        metadata={"amount": amount, "description": description},
    )
    return entry


def debit(
    member_id: int,
    amount: float,
    order_id: int | None = None,
    actor_id: int | None = None,
) -> StoredValueLedger:
    """Debit stored value. Validates sufficient balance and risk checks."""
    if amount is None or amount <= 0:
        raise StoredValueError("amount must be positive")

    member = db.session.get(Member, member_id)
    if member is None:
        raise StoredValueError("member not found")

    # Check risk flag before allowing debit
    if risk_service.has_active_member_flag(member.id, "spend_abuse"):
        raise StoredValueError("debit blocked by risk flag")

    current_balance = _get_encrypted_balance(member)
    if amount > current_balance:
        raise StoredValueError("insufficient stored-value balance")

    entry = StoredValueLedger(
        member_id=member.id,
        type="debit",
        amount=amount,
        order_id=order_id,
        description=None,
        created_at=datetime.utcnow(),
    )
    db.session.add(entry)

    _set_encrypted_balance(member, current_balance - amount)

    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="stored_value_debit",
        resource=f"member:{member.id}",
        metadata={"amount": amount, "order_id": order_id},
    )

    # Post-debit risk check: over $200/day triggers flag
    _check_daily_spend(member.id, actor_id=actor_id)

    return entry


def get_balance(member_id: int) -> float:
    """Return current balance from ledger sum."""
    credits = (
        db.session.query(db.func.coalesce(db.func.sum(StoredValueLedger.amount), 0.0))
        .filter(
            StoredValueLedger.member_id == member_id,
            StoredValueLedger.type == "credit",
        )
        .scalar()
    )
    debits = (
        db.session.query(db.func.coalesce(db.func.sum(StoredValueLedger.amount), 0.0))
        .filter(
            StoredValueLedger.member_id == member_id,
            StoredValueLedger.type == "debit",
        )
        .scalar()
    )
    return float(credits) - float(debits)


def get_history(member_id: int) -> list[StoredValueLedger]:
    """Return all ledger entries for a member, newest first."""
    return (
        StoredValueLedger.query.filter_by(member_id=member_id)
        .order_by(StoredValueLedger.created_at.desc())
        .all()
    )


def _check_daily_spend(member_id: int, *, actor_id: int | None = None) -> None:
    """Check if the member has exceeded the daily stored-value spend limit.

    Triggers a risk flag if over $200 spent today.
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    today_debits = StoredValueLedger.query.filter(
        StoredValueLedger.member_id == member_id,
        StoredValueLedger.type == "debit",
        StoredValueLedger.created_at >= today_start,
    ).all()

    total_spend = sum(e.amount for e in today_debits)

    if risk_service.check_spend_abuse(member_id, total_spend):
        risk_service.flag_member(
            member_id, "spend_abuse", actor_id=actor_id
        )
