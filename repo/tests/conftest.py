"""Shared pytest fixtures."""
import os
import shutil
import sys

sys.dont_write_bytecode = True
from datetime import datetime, timedelta

# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from app import create_app
from app.db import db
from app.services import auth_service, member_service
from config import TestConfig


@pytest.fixture(scope="session", autouse=True)
def _cleanup_pycache():
    """Remove __pycache__ dirs from source tree after the test session."""
    yield
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".venv"]
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
                dirnames.remove(d)


@pytest.fixture()
def app(tmp_path):
    application = create_app(TestConfig)
    application.config["EXPORT_DIR"] = str(tmp_path / "exports")
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


# --- Phase 1 user fixtures ---

@pytest.fixture()
def staff_user(app):
    """A seeded staff user."""
    return auth_service.register("staff1", "pw-staff-123", roles=["staff"])


@pytest.fixture()
def admin_user(app):
    return auth_service.register("admin1", "pw-admin-123", roles=["admin"])


@pytest.fixture()
def kitchen_user(app):
    return auth_service.register("kitchen1", "pw-kitchen-123", roles=["kitchen"])


@pytest.fixture()
def photographer_user(app):
    return auth_service.register("photo1", "pw-photo-123", roles=["photographer"])


@pytest.fixture()
def seeded_member(app, staff_user):
    return member_service.create_member(
        name="Jane Doe",
        phone_number="5551234567",
        member_id="M-TEST0001",
        actor_id=staff_user.id,
    )


# --- Logged-in session fixtures ---

@pytest.fixture()
def logged_in_staff(client, staff_user):
    """Log in the staff user via the JSON API."""
    resp = client.post(
        "/api/auth/login",
        json={"username": staff_user.username, "password": "pw-staff-123"},
    )
    assert resp.status_code == 200
    return staff_user


@pytest.fixture()
def logged_in_admin(client, admin_user):
    resp = client.post(
        "/api/auth/login",
        json={"username": admin_user.username, "password": "pw-admin-123"},
    )
    assert resp.status_code == 200
    return admin_user


@pytest.fixture()
def logged_in_kitchen(client, kitchen_user):
    resp = client.post(
        "/api/auth/login",
        json={"username": kitchen_user.username, "password": "pw-kitchen-123"},
    )
    assert resp.status_code == 200
    return kitchen_user


@pytest.fixture()
def logged_in_photographer(client, photographer_user):
    resp = client.post(
        "/api/auth/login",
        json={"username": photographer_user.username, "password": "pw-photo-123"},
    )
    assert resp.status_code == 200
    return photographer_user


# --- Enrollment fixture for clock-in tests ---

@pytest.fixture()
def enrolled_staff(app, staff_user):
    """Create an enrollment record for the staff user."""
    import hashlib
    from app.models.enrollment import Enrollment

    enrollment = Enrollment(
        user_id=staff_user.id,
        reference_hash=hashlib.sha256(b"test-reference").hexdigest(),
        device_id="kiosk-01",
        active=True,
    )
    db.session.add(enrollment)
    db.session.commit()
    return staff_user


# --- Phase 2 helper fixtures ---

@pytest.fixture()
def future_booking_times():
    """Return start/end datetimes 1 day in the future."""
    start = datetime.utcnow().replace(microsecond=0) + timedelta(days=1)
    end = start + timedelta(hours=1)
    return start, end
