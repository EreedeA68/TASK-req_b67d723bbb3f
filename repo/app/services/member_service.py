"""Member domain service — with Phase 3 encryption and masking."""
import hashlib
import hmac
import re
import uuid

from flask import current_app
from sqlalchemy import or_

from app.core.encryption import decrypt, encrypt, mask_balance, mask_phone
from app.db import db
from app.models.member import Member
from app.services import audit_service


class MemberError(Exception):
    """Error in member operations."""


def _clean(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_phone(phone: str) -> str:
    """Strip whitespace and non-digit formatting for consistent hashing."""
    return re.sub(r"\D+", "", phone or "")


def _phone_hash(phone: str) -> str:
    """Deterministic keyed HMAC-SHA256 of the normalized phone.

    Using HMAC with the server secret prevents offline rainbow-table lookups
    against leaked phone_hash values.  Result is indexed for fast lookup.
    """
    normalized = _normalize_phone(phone)
    if not normalized:
        return ""
    secret = current_app.config.get("SECRET_KEY", "").encode()
    return hmac.new(secret, normalized.encode(), hashlib.sha256).hexdigest()


def create_member(
    name: str,
    phone_number: str,
    *,
    tier: str = "standard",
    member_id: str | None = None,
    stored_value_balance: str = "0",
    actor_id: int | None = None,
) -> Member:
    name_c = _clean(name)
    phone_c = _clean(phone_number)
    if not name_c:
        raise MemberError("name is required")
    if not phone_c:
        raise MemberError("phone_number is required")

    if member_id is None or not str(member_id).strip():
        member_id = f"M-{uuid.uuid4().hex[:8].upper()}"
    else:
        member_id = str(member_id).strip()

    if Member.query.filter_by(member_id=member_id).first():
        raise MemberError("member_id already exists")

    member = Member(
        name=name_c,
        phone_number=encrypt(phone_c),
        phone_hash=_phone_hash(phone_c),
        member_id=member_id,
        tier=(tier or "standard").strip() or "standard",
        stored_value_balance=encrypt(str(stored_value_balance)),
    )
    db.session.add(member)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="member_created",
        resource=f"member:{member.id}",
        metadata={"member_id": member.member_id},
    )
    return member


# --------------- decryption + masking helpers ---------------

def _decrypt_phone(member: Member) -> str:
    """Return the plaintext phone number."""
    raw = member.phone_number or ""
    decrypted = decrypt(raw)
    return decrypted if decrypted else raw  # fallback for unencrypted legacy data


def _decrypt_balance(member: Member) -> str:
    raw = member.stored_value_balance or "0"
    decrypted = decrypt(raw)
    return decrypted if decrypted else raw


def member_to_dict(
    member: Member,
    *,
    is_admin: bool = False,
    restricted_fields: set[str] | None = None,
    allowed_fields: set[str] | None = None,
) -> dict:
    """Serialize a member, applying masking based on role and ABAC grants.

    Rules:
    - Admin sees every field raw *unless* that field appears in
      ``restricted_fields`` (admin-side restriction).
    - Non-admin masks sensitive fields *unless* that field appears in
      ``allowed_fields`` (explicit grant unmasks).

    This honors admin-configured field-level ABAC: a ScopePermission with
    scope_type="field" and scope_value="phone_number" will unmask the
    phone for roles granted that permission, matching the prompt's
    requirement that admins can configure field-level visibility.
    """
    phone_plain = _decrypt_phone(member)
    balance_plain = _decrypt_balance(member)
    restricted = restricted_fields or set()
    allowed = allowed_fields or set()

    # phone_number and stored_value_balance are "highly sensitive" — default
    # masked for non-admin unless explicitly granted.  points_balance is
    # considered "operationally visible" — staff need it at checkout — so it
    # is shown by default for non-admin unless explicitly restricted.
    def _visible_sensitive(field: str) -> bool:
        if is_admin:
            return field not in restricted
        return field in allowed

    def _visible_points() -> bool:
        if "points_balance" in restricted:
            return False
        return True

    # Include tier benefits from TierRule for UX surfacing
    from app.models.tier_rule import TierRule
    tier_rule = TierRule.query.filter_by(tier_name=member.tier).first()
    tier_benefits = tier_rule.benefits_list() if tier_rule else []
    tier_description = tier_rule.description if tier_rule else None
    tier_max_discount = tier_rule.max_discount_pct if tier_rule else 0.0

    return {
        "id": member.id,
        "name": member.name,
        "phone_number": phone_plain if _visible_sensitive("phone_number") else mask_phone(phone_plain),
        "member_id": member.member_id,
        "tier": member.tier,
        "tier_description": tier_description,
        "tier_benefits": tier_benefits,
        "tier_max_discount_pct": tier_max_discount,
        "points_balance": member.points_balance if _visible_points() else "***",
        "stored_value_balance": balance_plain if _visible_sensitive("stored_value_balance") else mask_balance(balance_plain),
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


# --------------- lookup / search ---------------

def lookup(query: str, *, actor_id: int | None = None) -> Member | None:
    """Lookup a member by member_id, or by scanning encrypted phone numbers."""
    q = _clean(query)
    if not q:
        raise MemberError("query must not be empty")

    # Try by member_id first (not encrypted)
    member = Member.query.filter_by(member_id=q).first()
    if member is None:
        # Scan for matching decrypted phone number
        member = _find_by_phone(q)

    audit_service.log(
        actor_id=actor_id,
        action="member_lookup",
        resource=f"member:{member.id if member else 'none'}",
        metadata={"query_hash": hashlib.sha256(q.encode()).hexdigest()[:16], "found": bool(member)},
    )
    return member


def _find_by_phone(phone: str) -> Member | None:
    """Indexed lookup via phone_hash, with a fallback scan for legacy rows."""
    h = _phone_hash(phone)
    if h:
        member = Member.query.filter_by(phone_hash=h).first()
        if member is not None:
            return member
    # Fallback: scan legacy rows without phone_hash (e.g., pre-migration data).
    normalized = _normalize_phone(phone)
    for m in Member.query.filter(Member.phone_hash.is_(None)).all():
        if _decrypt_phone(m) == phone or _normalize_phone(_decrypt_phone(m)) == normalized:
            return m
    return None


def search(query: str, *, actor_id: int | None = None) -> list[Member]:
    """Search by member_id or name (LIKE). Phone match via scan."""
    q = _clean(query)
    if not q:
        raise MemberError("query must not be empty")
    like = f"%{q}%"

    # member_id and name are not encrypted — LIKE works
    results = list(
        Member.query.filter(
            or_(
                Member.member_id.like(like),
                Member.name.like(like),
            )
        ).all()
    )
    # Also scan decrypted phone numbers for partial match
    seen_ids = {m.id for m in results}
    for m in Member.query.all():
        if m.id not in seen_ids and q in _decrypt_phone(m):
            results.append(m)

    audit_service.log(
        actor_id=actor_id,
        action="member_search",
        resource="member:collection",
        metadata={"query_hash": hashlib.sha256(q.encode()).hexdigest()[:16], "count": len(results)},
    )
    return results


def get_by_id(member_id: int) -> Member | None:
    return db.session.get(Member, member_id)
