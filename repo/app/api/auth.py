"""Auth JSON API — register, login, logout."""
from flask import Blueprint, jsonify, request

from app.core.rbac import get_current_user, login_required
from app.services import auth_service
from app.services.auth_service import AuthError

auth_api_bp = Blueprint("auth_api", __name__)


@auth_api_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    # Public registration always assigns the default "member" role.
    # Role assignment is an admin-only operation via a separate endpoint.
    try:
        user = auth_service.register(username, password)
    except AuthError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(user.to_dict()), 201


@auth_api_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    try:
        user = auth_service.authenticate(username, password)
    except AuthError as exc:
        return jsonify({"error": str(exc)}), 401
    auth_service.login(user)
    return jsonify({"message": "logged in", "user": user.to_dict()})


@auth_api_bp.post("/logout")
@login_required
def logout():
    auth_service.logout()
    return jsonify({"message": "logged out"})


@auth_api_bp.get("/me")
@login_required
def me():
    user = get_current_user()
    return jsonify(user.to_dict())
