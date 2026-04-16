"""Permission management service — configurable RBAC/ABAC scope layer."""
from app.db import db
from app.models.scope_permission import ScopePermission
from app.services import audit_service


def grant_permission(
    role_name: str,
    resource: str,
    action: str,
    scope_type: str | None = None,
    scope_value: str | None = None,
    actor_id: int | None = None,
) -> ScopePermission:
    """Create a new scope permission and log the change to the audit trail."""
    perm = ScopePermission(
        role_name=role_name,
        resource=resource,
        action=action,
        scope_type=scope_type,
        scope_value=scope_value,
        granted=True,
        created_by=actor_id,
    )
    db.session.add(perm)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="permission_granted",
        resource=f"scope_permission:{perm.id}",
        metadata={
            "role_name": role_name,
            "resource": resource,
            "action": action,
            "scope_type": scope_type,
            "scope_value": scope_value,
        },
    )
    return perm


def revoke_permission(permission_id: int, actor_id: int | None = None) -> bool:
    """Delete a scope permission by id and log the change to the audit trail.

    Returns True if the permission existed and was deleted, False otherwise.
    """
    perm = db.session.get(ScopePermission, permission_id)
    if perm is None:
        return False

    perm_dict = perm.to_dict()
    db.session.delete(perm)
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="permission_revoked",
        resource=f"scope_permission:{permission_id}",
        metadata=perm_dict,
    )
    return True


def list_permissions(role_name: str | None = None) -> list[ScopePermission]:
    """Return all scope permissions, optionally filtered by role."""
    query = ScopePermission.query
    if role_name:
        query = query.filter_by(role_name=role_name)
    return query.order_by(ScopePermission.id).all()


def check_scope(user, resource: str, action: str, context: dict | None = None) -> bool:
    """Check whether the user's role satisfies scope-level constraints.

    Logic:
    - Collect all ScopePermission records that match any of the user's roles
      for the given resource+action and have granted=True.
    - If there are NO such records, return True (no scope constraints apply;
      the static RBAC result stands).
    - If there ARE records, at least one must match the provided context:
        * A record with scope_type=None and scope_value=None is an
          unrestricted grant and always matches.
        * Otherwise the record's scope_type must be a key in context and
          scope_value must equal context[scope_type].
    - If records exist but none match the context, deny (return False).
    """
    if user is None:
        return False

    role_names = user.role_names()
    if not role_names:
        return False

    # Only consider operational scope records (location/station/employee).
    # Field-level and record-level scopes are enforced separately by
    # get_restricted_fields() and check_record_access().
    records = (
        ScopePermission.query
        .filter(
            ScopePermission.role_name.in_(role_names),
            ScopePermission.resource == resource,
            ScopePermission.action == action,
            ScopePermission.granted.is_(True),
            db.or_(
                ScopePermission.scope_type.is_(None),
                ~ScopePermission.scope_type.in_(["field", "record"]),
            ),
        )
        .all()
    )

    # No operational scope records => no additional constraints.
    if not records:
        return True

    context = context or {}

    for rec in records:
        # Unrestricted grant — scope_type and scope_value both null.
        if rec.scope_type is None and rec.scope_value is None:
            return True
        # Scoped grant — match against context.
        if rec.scope_type and rec.scope_type in context:
            if context[rec.scope_type] == rec.scope_value:
                return True

    # Records exist but none matched the context.
    return False


def get_restricted_fields(user, resource: str, action: str = "view") -> set[str]:
    """Return the set of field names that should be masked/hidden for this user.

    Checks ScopePermission records with scope_type="field".  If any such
    records exist for the user's role+resource+action, only the fields
    explicitly listed in scope_value are *visible*; all others in the
    sensitive set are restricted.  If no field-scope records exist, the
    default masking rules apply (empty set returned).
    """
    if user is None:
        return set()

    role_names = user.role_names()
    if "admin" in role_names:
        return set()  # admins see everything

    records = (
        ScopePermission.query
        .filter(
            ScopePermission.role_name.in_(role_names),
            ScopePermission.resource == resource,
            ScopePermission.action == action,
            ScopePermission.scope_type == "field",
            ScopePermission.granted.is_(True),
        )
        .all()
    )

    if not records:
        return set()  # no field-level scope configured; default masking applies

    # Collect explicitly allowed fields
    allowed_fields = {rec.scope_value for rec in records if rec.scope_value}

    # Sensitive fields that require explicit permission
    SENSITIVE_FIELDS = {"phone_number", "stored_value_balance", "points_balance"}
    return SENSITIVE_FIELDS - allowed_fields


def get_allowed_fields(user, resource: str, action: str = "view") -> set[str]:
    """Return the set of sensitive fields explicitly granted to this user.

    Admin always gets the full sensitive set.  Non-admin gets only the
    specific fields listed in ScopePermission(scope_type="field") grants
    for any of their roles.  Used by serializers to selectively unmask
    fields beyond the default admin-only visibility.
    """
    SENSITIVE_FIELDS = {"phone_number", "stored_value_balance", "points_balance"}
    if user is None:
        return set()

    role_names = user.role_names()
    if "admin" in role_names:
        return set(SENSITIVE_FIELDS)

    records = (
        ScopePermission.query
        .filter(
            ScopePermission.role_name.in_(role_names),
            ScopePermission.resource == resource,
            ScopePermission.action == action,
            ScopePermission.scope_type == "field",
            ScopePermission.granted.is_(True),
        )
        .all()
    )
    return {rec.scope_value for rec in records if rec.scope_value and rec.scope_value in SENSITIVE_FIELDS}


def check_record_access(
    user, resource: str, action: str, record_id: int
) -> bool:
    """Check whether a user has record-level scope access to a specific record.

    If no record-scope constraints exist, returns True (default allow).
    If constraints exist, at least one must match the record_id.
    """
    if user is None:
        return False

    role_names = user.role_names()
    if "admin" in role_names:
        return True

    records = (
        ScopePermission.query
        .filter(
            ScopePermission.role_name.in_(role_names),
            ScopePermission.resource == resource,
            ScopePermission.action == action,
            ScopePermission.scope_type == "record",
            ScopePermission.granted.is_(True),
        )
        .all()
    )

    if not records:
        return True  # no record-level scope configured

    return any(
        rec.scope_value == str(record_id)
        for rec in records
    )
