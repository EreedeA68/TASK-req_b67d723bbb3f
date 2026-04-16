"""Auth views — login page + login/logout form handlers."""
from flask import Blueprint, make_response, redirect, render_template, request, url_for

from app.core.rbac import get_current_user, login_required
from app.services import auth_service
from app.services.auth_service import AuthError

auth_view_bp = Blueprint("auth_view", __name__)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


@auth_view_bp.get("/login")
def login_page():
    if get_current_user() is not None:
        return redirect(url_for("members_view.members_page"))
    return render_template("login.html", error=None)


@auth_view_bp.post("/auth/login")
def do_login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    try:
        user = auth_service.authenticate(username, password)
    except AuthError as exc:
        if _is_htmx():
            return render_template(
                "partials/login_error.html", error=str(exc)
            ), 401
        return render_template("login.html", error=str(exc)), 401

    auth_service.login(user)

    if _is_htmx():
        resp = make_response(
            render_template("partials/login_success.html", user=user)
        )
        resp.headers["HX-Redirect"] = url_for("members_view.members_page")
        return resp
    return redirect(url_for("members_view.members_page"))


@auth_view_bp.post("/auth/logout")
@login_required
def do_logout():
    auth_service.logout()
    return redirect(url_for("auth_view.login_page"))
