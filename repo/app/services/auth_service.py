"""Authentication / registration service."""
from flask import request, session

from app.core.security import hash_password, verify_password
from app.db import db
from app.models.role import Role
from app.models.user import User
from app.services import audit_service


class AuthError(Exception):
    """Authentication or registration failure."""


def register(
    username: str,
    password: str,
    roles: list[str] | None = None,
) -> User:
    """Create a new user with optional role names."""
    if not isinstance(username, str) or not isinstance(password, str):
        raise AuthError("username and password are required")
    username = username.strip()
    if not username or not password:
        raise AuthError("username and password are required")
    if User.query.filter_by(username=username).first():
        raise AuthError("username already exists")

    user = User(username=username, password_hash=hash_password(password))
    if roles:
        role_objs = Role.query.filter(Role.name.in_(roles)).all()
        user.roles = role_objs
    else:
        # Default to plain "member" role if no role supplied.
        default = Role.query.filter_by(name="member").first()
        if default:
            user.roles = [default]

    db.session.add(user)
    db.session.commit()
    return user


def authenticate(username: str, password: str) -> User:
    """Look up a user and verify their password.

    Logs every failed attempt to the audit log.
    """
    if not isinstance(username, str):
        username = ""
    username = username.strip()
    remote_addr = ""
    try:
        remote_addr = request.remote_addr or ""
    except RuntimeError:
        # No request context (e.g. direct service-layer test).
        pass

    user = User.query.filter_by(username=username).first()
    if user is None or not verify_password(password or "", user.password_hash):
        audit_service.log(
            actor_id=user.id if user else None,
            action="login_failed",
            resource=f"user:{username or 'unknown'}",
            metadata={
                "username": username,
                "reason": "unknown_user" if user is None else "bad_password",
                "remote_addr": remote_addr,
            },
        )
        raise AuthError("invalid credentials")
    return user


def login(user: User) -> None:
    """Establish a session for this user."""
    session.clear()
    session["user_id"] = user.id
    audit_service.log(
        actor_id=user.id,
        action="login",
        resource=f"user:{user.id}",
        metadata={"username": user.username},
    )


def logout() -> None:
    """Invalidate the current session."""
    user_id = session.get("user_id")
    # Defense in depth — pop known keys, then clear everything.
    session.pop("user_id", None)
    session.clear()
    if user_id:
        audit_service.log(
            actor_id=user_id,
            action="logout",
            resource=f"user:{user_id}",
            metadata={},
        )


# ---------- Admin user-role management ----------

def assign_roles(
    user_id: int,
    role_names: list[str],
    *,
    actor_id: int | None = None,
) -> User:
    """Replace a user's roles with the given list.  Admin-only operation."""
    user = db.session.get(User, user_id)
    if user is None:
        raise AuthError("user not found")

    role_objs = Role.query.filter(Role.name.in_(role_names)).all()
    found = {r.name for r in role_objs}
    missing = [n for n in role_names if n not in found]
    if missing:
        raise AuthError(f"unknown role(s): {', '.join(missing)}")

    prev = user.role_names()
    user.roles = role_objs
    db.session.commit()

    audit_service.log(
        actor_id=actor_id,
        action="user_roles_assigned",
        resource=f"user:{user_id}",
        metadata={"from": prev, "to": list(found)},
    )
    return user


def add_role(
    user_id: int,
    role_name: str,
    *,
    actor_id: int | None = None,
) -> User:
    """Add a single role to a user if not already present."""
    user = db.session.get(User, user_id)
    if user is None:
        raise AuthError("user not found")
    role = Role.query.filter_by(name=role_name).first()
    if role is None:
        raise AuthError(f"unknown role: {role_name}")
    if role in user.roles:
        return user
    user.roles.append(role)
    db.session.commit()
    audit_service.log(
        actor_id=actor_id,
        action="user_role_added",
        resource=f"user:{user_id}",
        metadata={"role": role_name},
    )
    return user


def remove_role(
    user_id: int,
    role_name: str,
    *,
    actor_id: int | None = None,
) -> User:
    """Remove a role from a user if present."""
    user = db.session.get(User, user_id)
    if user is None:
        raise AuthError("user not found")
    role = next((r for r in user.roles if r.name == role_name), None)
    if role is None:
        return user  # no-op
    user.roles.remove(role)
    db.session.commit()
    audit_service.log(
        actor_id=actor_id,
        action="user_role_removed",
        resource=f"user:{user_id}",
        metadata={"role": role_name},
    )
    return user


def list_users() -> list[User]:
    """List all users (admin-only)."""
    return User.query.order_by(User.id).all()
