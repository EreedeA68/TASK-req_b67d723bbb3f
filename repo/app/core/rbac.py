"""RBAC permission structure and decorators."""
from functools import wraps

from flask import jsonify, request, session


# Permission structure: resource -> {action -> [roles allowed]}
PERMISSIONS = {
    "member": {
        "view": ["admin", "staff", "photographer", "kitchen"],
        "search": ["admin", "staff", "photographer", "kitchen"],
        "create": ["admin", "staff"],
    },
    "order": {
        "view": ["admin", "staff", "kitchen"],
        "create": ["admin", "staff"],
        "pay": ["admin", "staff"],
        "advance": ["admin", "staff", "kitchen"],
    },
    "audit": {
        "view": ["admin"],
    },
    "schedule": {
        "view": ["admin", "staff", "photographer"],
        "create": ["admin", "staff"],
    },
    "booking": {
        "view": ["admin", "staff", "photographer"],
        "create": ["admin", "staff"],
        "confirm": ["admin", "staff"],
        "cancel": ["admin", "staff"],
    },
    "kds": {
        "view": ["admin", "staff", "kitchen"],
        "start": ["admin", "kitchen"],
        "complete": ["admin", "kitchen"],
    },
    "search": {
        "perform": ["admin", "staff", "photographer", "kitchen"],
        "trending": ["admin", "staff"],
    },
    "clockin": {
        "submit": ["admin", "staff", "photographer", "kitchen"],
    },
    "risk": {
        "view": ["admin", "staff"],
        "clear": ["admin"],
    },
    "export": {
        "create": ["admin", "staff"],
        "view": ["admin", "staff"],
    },
    "versioning": {
        "snapshot": ["admin"],
        "rollback": ["admin"],
        "view": ["admin"],
    },
    "permission": {
        "view": ["admin"],
        "manage": ["admin"],
    },
    "user": {
        "view": ["admin"],
        "manage": ["admin"],
    },
    "enrollment": {
        "view": ["admin"],
        "manage": ["admin"],
    },
    "correction": {
        "submit": ["admin", "staff", "photographer", "kitchen"],
        "review": ["admin"],
    },
}


def get_current_user():
    """Return the current logged-in user (or None)."""
    from app.db import db
    from app.models.user import User

    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def has_permission(user, resource: str, action: str, context: dict | None = None) -> bool:
    """Check static RBAC and, when applicable, configurable scope constraints.

    If the static RBAC check passes **and** there are ScopePermission records
    for the user's role+resource+action, the scope constraints must also be
    satisfied.  If no scope records exist the static RBAC result stands.
    """
    if user is None:
        return False
    allowed_roles = PERMISSIONS.get(resource, {}).get(action, [])
    user_roles = user.role_names()
    if "admin" in user_roles:
        return True
    if not any(r in allowed_roles for r in user_roles):
        return False

    # Static RBAC passed — now layer on configurable scope constraints.
    from app.services import permission_service

    return permission_service.check_scope(user, resource, action, context=context)


def _wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept


def _audit_unauthorized(action: str, user_id: int | None = None) -> None:
    """Best-effort audit of a denial — never raise from the decorator."""
    try:
        from app.services import audit_service

        audit_service.log(
            actor_id=user_id,
            action=action,
            resource=f"route:{request.method} {request.path}",
            metadata={"remote_addr": request.remote_addr or ""},
        )
    except Exception:  # pragma: no cover — audit must not break the request
        from app.db import db

        try:
            db.session.rollback()
        except Exception:
            pass


def _unauth_response():
    if _wants_json():
        return jsonify({"error": "authentication required"}), 401
    from flask import redirect, url_for

    return redirect(url_for("auth_view.login_page"))


def _forbidden_response():
    if _wants_json():
        return jsonify({"error": "forbidden"}), 403
    return ("Forbidden", 403)


def login_required(view):
    """Ensure a user is authenticated. Logs unauthorized access attempts."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user is None:
            _audit_unauthorized("unauthorized_access")
            return _unauth_response()
        return view(*args, **kwargs)

    return wrapper


def _build_request_context() -> dict:
    """Build ABAC context from the current request for scope enforcement.

    Supports location/station/employee (operational scope) extracted from
    query params or X-Scope-* headers.  Record-level context is derived
    exclusively from server-side route params (view_args) to prevent
    clients from injecting arbitrary record IDs via query strings.

    The canonical "record" key is set from the first ``*_id`` view_arg,
    ensuring ``check_scope`` sees ``context["record"]`` matching
    ``ScopePermission.scope_value``.
    """
    ctx = {}
    # Operational scope — safe to read from client context since these are
    # advisory selectors (the scope layer validates them against grants).
    for key in ("location", "station", "employee"):
        val = request.args.get(key) or request.headers.get(f"X-Scope-{key.title()}")
        if val:
            ctx[key] = val

    # Record-level context — derived from server-side route params only.
    # Canonicalize the first *_id view_arg into the "record" key so that
    # check_scope can match ScopePermission(scope_type="record").
    if request.view_args:
        for k, v in request.view_args.items():
            if k.endswith("_id"):
                ctx["record"] = str(v)
                break  # use the primary resource ID

    # API-scope context — the request path, for ScopePermission(scope_type="api").
    ctx["api"] = request.path

    # Menu-scope context — derived from the resource being accessed.
    # The menu scope_value matches the URL prefix (e.g., "orders", "members").
    parts = request.path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "api":
        ctx["menu"] = parts[1]
    elif parts:
        ctx["menu"] = parts[0]

    return ctx


def permission_required(resource: str, action: str, *, record_scope: bool = False):
    """Require a specific permission with ABAC scope context. Logs denials.

    If ``record_scope=True``, additionally enforces record-level scope using
    the primary ``*_id`` view_arg as the record id.  This provides uniform
    enforcement across resources (orders, bookings, exports, etc.) without
    each endpoint hand-rolling the check.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user is None:
                _audit_unauthorized("unauthorized_access")
                return _unauth_response()
            context = _build_request_context()
            if not has_permission(user, resource, action, context=context):
                _audit_unauthorized("permission_denied", user_id=user.id)
                return _forbidden_response()

            if record_scope:
                from app.services import permission_service

                record_id = None
                for k, v in (request.view_args or {}).items():
                    if k.endswith("_id"):
                        try:
                            record_id = int(v)
                        except (TypeError, ValueError):
                            record_id = None
                        break
                if record_id is not None:
                    if not permission_service.check_record_access(
                        user, resource, action, record_id,
                    ):
                        _audit_unauthorized(
                            "record_scope_denied", user_id=user.id
                        )
                        return _forbidden_response()
            return view(*args, **kwargs)

        return wrapper

    return decorator
