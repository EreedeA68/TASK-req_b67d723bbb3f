"""Data versioning and validation tests."""


def test_snapshot_member(app, logged_in_admin, seeded_member):
    from app.models.audit import AuditLog
    from app.models.versioning import DataVersion
    from app.services import versioning_service

    version = versioning_service.create_snapshot(
        "member", seeded_member.id, actor_id=logged_in_admin.id
    )
    assert version.entity_type == "member"
    snap = version.get_snapshot()
    assert snap["name"] == seeded_member.name
    assert snap["member_id"] == seeded_member.member_id
    assert DataVersion.query.count() == 1
    assert AuditLog.query.filter_by(action="version_snapshot").count() == 1


def test_snapshot_order(app, logged_in_admin, seeded_member, client):
    from app.services import order_service, versioning_service

    order = order_service.create_order(
        member_id=seeded_member.id, subtotal=50.0
    )
    version = versioning_service.create_snapshot(
        "order", order.id, actor_id=logged_in_admin.id
    )
    snap = version.get_snapshot()
    assert snap["status"] == "created"
    assert snap["subtotal"] == 50.0


def test_rollback_member(app, logged_in_admin, seeded_member):
    from app.db import db
    from app.models.audit import AuditLog
    from app.services import versioning_service

    # Snapshot with original name
    versioning_service.create_snapshot("member", seeded_member.id)
    # Change the name
    seeded_member.name = "Changed Name"
    db.session.commit()
    assert seeded_member.name == "Changed Name"
    # Rollback
    snap = versioning_service.rollback("member", seeded_member.id)
    assert snap["name"] == "Jane Doe"
    assert seeded_member.name == "Jane Doe"
    assert AuditLog.query.filter_by(action="version_rollback").count() == 1


def test_rollback_no_snapshot_raises(app, logged_in_admin, seeded_member):
    from app.services.versioning_service import VersioningError
    import pytest

    with pytest.raises(VersioningError, match="no snapshot found"):
        from app.services import versioning_service
        versioning_service.rollback("member", seeded_member.id)


def test_snapshot_unknown_entity_raises(app, logged_in_admin):
    from app.services.versioning_service import VersioningError
    import pytest

    with pytest.raises(VersioningError, match="unsupported"):
        from app.services import versioning_service
        versioning_service.create_snapshot("foo", 1)


def test_validate_member_ok(app, seeded_member):
    from app.services import versioning_service

    errors = versioning_service.validate_member(seeded_member)
    assert errors == []


def test_validate_member_detects_issues(app, seeded_member):
    from app.db import db
    from app.models.audit import AuditLog
    from app.services import versioning_service

    seeded_member.name = ""
    seeded_member.points_balance = -5
    db.session.commit()
    errors = versioning_service.validate_member(seeded_member)
    assert any("name" in e for e in errors)
    assert any("points_balance" in e for e in errors)
    assert AuditLog.query.filter_by(action="validation_error").count() >= 2


def test_version_api_snapshot(client, logged_in_admin, seeded_member):
    resp = client.post(f"/api/versions/member/{seeded_member.id}/snapshot", json={})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["entity_type"] == "member"
    assert data["snapshot"]["name"] == seeded_member.name


def test_version_api_rollback(client, logged_in_admin, seeded_member, app):
    from app.db import db

    client.post(f"/api/versions/member/{seeded_member.id}/snapshot", json={})
    seeded_member.name = "API Changed"
    db.session.commit()
    resp = client.post(f"/api/versions/member/{seeded_member.id}/rollback", json={})
    assert resp.status_code == 200
    assert resp.get_json()["restored"]["name"] == "Jane Doe"


def test_version_api_requires_admin(client, logged_in_staff, seeded_member):
    resp = client.post(f"/api/versions/member/{seeded_member.id}/snapshot", json={})
    assert resp.status_code == 403


def test_version_ui_page(client, logged_in_admin):
    resp = client.get("/versions")
    assert resp.status_code == 200
    assert b"Versioning" in resp.data


def test_snapshot_unsupported_entity_in_rollback(app, logged_in_admin):
    import pytest
    from app.services import versioning_service
    from app.services.versioning_service import VersioningError

    with pytest.raises(VersioningError, match="unsupported"):
        versioning_service.rollback("spaceship", 1)


def test_snapshot_entity_not_found_raises(app, logged_in_admin):
    import pytest
    from app.services import versioning_service
    from app.services.versioning_service import VersioningError

    with pytest.raises(VersioningError, match="not found"):
        versioning_service.create_snapshot("member", 99999)


def test_rollback_order(app, logged_in_admin, seeded_member):
    from app.services import order_service, versioning_service

    order = order_service.create_order(member_id=seeded_member.id, subtotal=30.0)
    versioning_service.create_snapshot("order", order.id)
    snap = versioning_service.rollback("order", order.id)
    assert snap["status"] == "created"
    assert snap["subtotal"] == 30.0


def test_list_versions(app, logged_in_admin, seeded_member):
    from app.services import versioning_service

    versioning_service.create_snapshot("member", seeded_member.id)
    versioning_service.create_snapshot("member", seeded_member.id)
    versions = versioning_service.list_versions("member", seeded_member.id)
    assert len(versions) == 2


def test_version_api_list(client, logged_in_admin, seeded_member):
    client.post(f"/api/versions/member/{seeded_member.id}/snapshot", json={})
    resp = client.get(f"/api/versions?entity_type=member&entity_id={seeded_member.id}")
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) >= 1


def test_validate_member_missing_member_id(app, seeded_member):
    from app.db import db
    from app.services.versioning_service import validate_member
    seeded_member.member_id = ""
    db.session.commit()
    errors = validate_member(seeded_member)
    assert any("member_id" in e for e in errors)


def test_validate_member_duplicate_member_id(app, seeded_member):
    from unittest.mock import MagicMock, patch
    from app.services.versioning_service import validate_member
    fake_dup = MagicMock()
    with patch("app.services.versioning_service.Member") as mock_member_cls:
        mock_member_cls.query.filter.return_value.first.return_value = fake_dup
        errors = validate_member(seeded_member)
    assert any("duplicate" in e for e in errors)


def test_validate_order_with_negative_values(app, seeded_member):
    from app.db import db
    from app.services import order_service
    from app.services.versioning_service import validate_order
    order = order_service.create_order(member_id=seeded_member.id, subtotal=10.0)
    order.subtotal = -1.0
    order.total = -1.0
    db.session.commit()
    errors = validate_order(order)
    assert len(errors) >= 1


def test_validate_order_valid(app, seeded_member):
    from app.services import order_service
    from app.services.versioning_service import validate_order
    order = order_service.create_order(member_id=seeded_member.id, subtotal=10.0)
    errors = validate_order(order)
    assert errors == []


def test_rollback_entity_deleted_raises(app, seeded_member):
    import pytest
    from app.db import db
    from app.services import versioning_service
    from app.services.versioning_service import VersioningError
    versioning_service.create_snapshot("member", seeded_member.id)
    mid = seeded_member.id
    db.session.delete(seeded_member)
    db.session.commit()
    with pytest.raises(VersioningError, match="not found"):
        versioning_service.rollback("member", mid)
