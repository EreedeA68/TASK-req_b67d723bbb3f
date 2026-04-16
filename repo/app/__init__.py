"""Flask application factory."""
import click
from flask import Flask, redirect, request, url_for
from flask_wtf.csrf import CSRFProtect

from config import Config
from app.db import db

csrf = CSRFProtect()


def create_app(config_class: type = Config) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(config_class)

    # Fail-fast on insecure defaults in non-test environments.
    if hasattr(config_class, "init_app"):
        config_class.init_app(app)

    # Extensions
    db.init_app(app)
    csrf.init_app(app)

    # Models must be imported so they register with SQLAlchemy metadata.
    from app.models import (  # noqa: F401
        user, member, order, audit, role,
        schedule, booking, kds, search,
        timepunch, punch_correction, enrollment,
        risk, export, versioning,
        points, scope_permission,
        stored_value, tier_rule, catalog,
        order_item, receipt,
    )

    # Blueprints — API
    from app.api.auth import auth_api_bp
    from app.api.members import members_api_bp
    from app.api.orders import orders_api_bp

    app.register_blueprint(auth_api_bp, url_prefix="/api/auth")
    app.register_blueprint(members_api_bp, url_prefix="/api/members")
    app.register_blueprint(orders_api_bp, url_prefix="/api/orders")

    from app.api.schedules import schedules_api_bp
    from app.api.bookings import bookings_api_bp
    from app.api.kds import kds_api_bp
    from app.api.search import search_api_bp

    app.register_blueprint(schedules_api_bp, url_prefix="/api/schedules")
    app.register_blueprint(bookings_api_bp, url_prefix="/api/bookings")
    app.register_blueprint(kds_api_bp, url_prefix="/api/kds")
    app.register_blueprint(search_api_bp, url_prefix="/api/search")

    from app.api.clockin import clockin_api_bp
    from app.api.risk import risk_api_bp
    from app.api.exports import exports_api_bp
    from app.api.versions import versions_api_bp

    app.register_blueprint(clockin_api_bp, url_prefix="/api")
    app.register_blueprint(risk_api_bp, url_prefix="/api/risk")
    app.register_blueprint(exports_api_bp, url_prefix="/api/exports")
    app.register_blueprint(versions_api_bp, url_prefix="/api/versions")

    from app.api.permissions import permissions_api_bp
    from app.api.points import points_api_bp
    from app.api.corrections import corrections_api_bp
    from app.api.stored_value import stored_value_api_bp
    from app.api.users import users_api_bp
    from app.api.enrollments import enrollments_api_bp
    from app.api.tiers import tiers_api_bp

    app.register_blueprint(permissions_api_bp, url_prefix="/api/permissions")
    app.register_blueprint(points_api_bp, url_prefix="/api/points")
    app.register_blueprint(corrections_api_bp, url_prefix="/api/corrections")
    app.register_blueprint(stored_value_api_bp, url_prefix="/api/stored-value")
    app.register_blueprint(users_api_bp, url_prefix="/api/users")
    app.register_blueprint(enrollments_api_bp, url_prefix="/api/enrollments")
    app.register_blueprint(tiers_api_bp, url_prefix="/api/tiers")

    # Exempt JSON API blueprints from Flask-WTF CSRF tokens (they use
    # session auth).  Instead, enforce Content-Type: application/json on
    # all mutating requests via a before_request hook — this prevents
    # cross-site form POSTs because browsers cannot set Content-Type to
    # application/json cross-origin without a CORS preflight.
    for bp in (
        auth_api_bp, members_api_bp, orders_api_bp,
        schedules_api_bp, bookings_api_bp, kds_api_bp, search_api_bp,
        clockin_api_bp, risk_api_bp, exports_api_bp, versions_api_bp,
        permissions_api_bp, points_api_bp, corrections_api_bp,
        stored_value_api_bp, users_api_bp, enrollments_api_bp,
        tiers_api_bp,
    ):
        csrf.exempt(bp)

    @app.before_request
    def _enforce_json_content_type():
        """Reject mutating API requests that lack JSON Content-Type.

        This is the primary CSRF defence for session-authenticated JSON
        APIs: browsers sending cross-origin form POSTs will use
        application/x-www-form-urlencoded or multipart/form-data, not
        application/json, and CORS preflight blocks custom content types.

        Enforced on *all* mutating methods regardless of body length —
        bodyless mutations (e.g. POST /api/auth/logout) must also require
        a JSON-indicating content-type (or an empty content-type that
        browsers can't forge cross-origin with CSRF, but we require
        application/json for uniformity).
        """
        if (
            request.path.startswith("/api/")
            and request.method in ("POST", "PUT", "PATCH", "DELETE")
        ):
            ct = (request.content_type or "").lower()
            # Reject any explicit form-like content type, and require
            # application/json when content type is supplied.  An empty
            # content-type with zero body is still rejected because
            # modern browsers always set a content-type on form POSTs.
            if "application/json" not in ct:
                from flask import jsonify as _j
                return _j({"error": "Content-Type must be application/json"}), 415

    # Blueprints — Views
    from app.views.auth import auth_view_bp
    from app.views.members import members_view_bp
    from app.views.orders import orders_view_bp

    app.register_blueprint(auth_view_bp)
    app.register_blueprint(members_view_bp)
    app.register_blueprint(orders_view_bp)

    from app.views.schedules import schedules_view_bp
    from app.views.bookings import bookings_view_bp
    from app.views.kds import kds_view_bp
    from app.views.search import search_view_bp

    app.register_blueprint(schedules_view_bp)
    app.register_blueprint(bookings_view_bp)
    app.register_blueprint(kds_view_bp)
    app.register_blueprint(search_view_bp)

    from app.views.clockin import clockin_view_bp
    from app.views.exports import exports_view_bp
    from app.views.risk import risk_view_bp
    from app.views.versions import versions_view_bp

    app.register_blueprint(clockin_view_bp)
    app.register_blueprint(exports_view_bp)
    app.register_blueprint(risk_view_bp)
    app.register_blueprint(versions_view_bp)

    @app.route("/")
    def index():
        return redirect(url_for("members_view.members_page"))

    with app.app_context():
        db.create_all()
        _seed_default_roles()

    # Flask CLI command for autonomous expiry processing
    @app.cli.command("check-expiry")
    def check_expiry_cmd():
        """Run a single expiry sweep on all orders."""
        from app.services.expiry_service import process_all_expired_orders

        result = process_all_expired_orders()
        click.echo(
            f"Expiry sweep complete: {result['cancelled']} cancelled, "
            f"{result['moved_to_pickup']} moved to pickup."
        )

    # Start background expiry ticker for non-test deployments
    from app.services.expiry_service import start_expiry_ticker
    start_expiry_ticker(app)

    return app


def _seed_default_roles() -> None:
    """Ensure standard roles and tier rules exist."""
    from app.models.role import Role
    from app.models.tier_rule import TierRule

    defaults = ["admin", "staff", "photographer", "kitchen", "member"]
    for name in defaults:
        if not Role.query.filter_by(name=name).first():
            db.session.add(Role(name=name))

    defaults_tiers = [
        ("standard", 0.05, "Entry tier",
         "Points on every purchase;Standard checkout discounts up to 5%"),
        ("silver", 0.10, "Regular visitor tier",
         "Points on every purchase;Silver discounts up to 10%;Priority photo review"),
        ("gold", 0.15, "Frequent visitor tier",
         "Points on every purchase;Gold discounts up to 15%;Priority photo review;Free photo reprint once per year"),
        ("platinum", 0.20, "Top-tier loyalty",
         "Points on every purchase;Platinum discounts up to 20%;Priority pickup;Free photo reprint anytime;Member-only events"),
    ]
    for name, pct, desc, benefits in defaults_tiers:
        existing = TierRule.query.filter_by(tier_name=name).first()
        if existing is None:
            db.session.add(TierRule(
                tier_name=name, max_discount_pct=pct,
                description=desc, benefits=benefits,
            ))
        else:
            # Populate benefits on pre-existing rows that lack them
            if not existing.benefits:
                existing.benefits = benefits
            if not existing.description:
                existing.description = desc

    db.session.commit()
