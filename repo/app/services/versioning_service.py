"""Data versioning and validation service."""
import json

from app.db import db
from app.models.member import Member
from app.models.order import Order
from app.models.versioning import DataVersion, ValidationError as VError
from app.services import audit_service
from app.services.member_service import _decrypt_balance, _decrypt_phone


class VersioningError(Exception):
    """Error in versioning operations."""


SUPPORTED_ENTITIES = {"member", "order"}


def _get_entity(entity_type: str, entity_id: int):
    if entity_type == "member":
        return db.session.get(Member, entity_id)
    if entity_type == "order":
        return db.session.get(Order, entity_id)
    return None


def _entity_snapshot(entity_type: str, entity) -> dict:
    """Build a snapshot dict for an entity."""
    if entity_type == "member":
        return {
            "id": entity.id,
            "name": entity.name,
            "phone_number": _decrypt_phone(entity),
            "member_id": entity.member_id,
            "tier": entity.tier,
            "points_balance": entity.points_balance,
            "stored_value_balance": _decrypt_balance(entity),
        }
    if entity_type == "order":
        return entity.to_dict()
    return {}


def create_snapshot(
    entity_type: str,
    entity_id: int,
    *,
    actor_id: int | None = None,
) -> DataVersion:
    if entity_type not in SUPPORTED_ENTITIES:
        raise VersioningError(f"unsupported entity type: {entity_type}")
    entity = _get_entity(entity_type, entity_id)
    if entity is None:
        raise VersioningError(f"{entity_type} {entity_id} not found")

    snap = _entity_snapshot(entity_type, entity)
    version = DataVersion(
        entity_type=entity_type,
        entity_id=entity_id,
        snapshot=json.dumps(snap),
    )
    db.session.add(version)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="version_snapshot",
        resource=f"{entity_type}:{entity_id}",
        metadata={"version_id": version.id},
    )
    return version


def rollback(
    entity_type: str,
    entity_id: int,
    *,
    actor_id: int | None = None,
) -> dict:
    """Restore the most recent snapshot for an entity."""
    if entity_type not in SUPPORTED_ENTITIES:
        raise VersioningError(f"unsupported entity type: {entity_type}")

    version = (
        DataVersion.query
        .filter_by(entity_type=entity_type, entity_id=entity_id)
        .order_by(DataVersion.created_at.desc())
        .first()
    )
    if version is None:
        raise VersioningError(f"no snapshot found for {entity_type}:{entity_id}")

    entity = _get_entity(entity_type, entity_id)
    if entity is None:
        raise VersioningError(f"{entity_type} {entity_id} not found")

    snap = version.get_snapshot()
    _apply_snapshot(entity_type, entity, snap)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="version_rollback",
        resource=f"{entity_type}:{entity_id}",
        metadata={"version_id": version.id, "snapshot": snap},
    )
    return snap


def _apply_snapshot(entity_type: str, entity, snap: dict) -> None:
    if entity_type == "member":
        from app.core.encryption import encrypt

        if "name" in snap:
            entity.name = snap["name"]
        if "phone_number" in snap:
            entity.phone_number = encrypt(snap["phone_number"])
        if "tier" in snap:
            entity.tier = snap["tier"]
        if "points_balance" in snap:
            entity.points_balance = snap["points_balance"]
        if "stored_value_balance" in snap:
            entity.stored_value_balance = encrypt(str(snap["stored_value_balance"]))
    elif entity_type == "order":
        if "status" in snap:
            entity.status = snap["status"]
        if "subtotal" in snap:
            entity.subtotal = snap["subtotal"]
        if "discount" in snap:
            entity.discount = snap["discount"]
        if "total" in snap:
            entity.total = snap["total"]


def list_versions(
    entity_type: str,
    entity_id: int,
) -> list[DataVersion]:
    return (
        DataVersion.query
        .filter_by(entity_type=entity_type, entity_id=entity_id)
        .order_by(DataVersion.created_at.desc())
        .all()
    )


# --------------- validation ---------------

def validate_member(member: Member) -> list[str]:
    """Run basic validation on a member. Returns list of error messages."""
    errors: list[str] = []
    if not member.name or not member.name.strip():
        errors.append("name is required")
    if not member.member_id:
        errors.append("member_id is required")
    if member.points_balance is not None and member.points_balance < 0:
        errors.append("points_balance must be >= 0")
    # Duplicate check
    dup = Member.query.filter(
        Member.member_id == member.member_id,
        Member.id != member.id,
    ).first()
    if dup:
        errors.append(f"duplicate member_id: {member.member_id}")

    for msg in errors:
        _record_validation_error("member", member.id, msg)
    return errors


def validate_order(order: Order) -> list[str]:
    errors: list[str] = []
    if order.subtotal is None or order.subtotal < 0:
        errors.append("subtotal must be >= 0")
    if order.total is None or order.total < 0:
        errors.append("total must be >= 0")

    for msg in errors:
        _record_validation_error("order", order.id, msg)
    return errors


def _record_validation_error(entity_type: str, entity_id: int, msg: str) -> None:
    ve = VError(entity_type=entity_type, entity_id=entity_id, error_message=msg)
    db.session.add(ve)
    db.session.commit()
    audit_service.log(
        actor_id=None,
        action="validation_error",
        resource=f"{entity_type}:{entity_id}",
        metadata={"error": msg},
    )
