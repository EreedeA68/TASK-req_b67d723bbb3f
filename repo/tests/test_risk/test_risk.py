"""Risk/fraud control tests."""


def test_flag_user(app, staff_user):
    from app.models.audit import AuditLog
    from app.services import risk_service

    flag = risk_service.flag_user(staff_user.id, "points_abuse")
    assert flag.active is True
    assert flag.type == "points_abuse"
    assert AuditLog.query.filter_by(action="risk_flag_triggered").count() == 1


def test_flag_idempotent(app, staff_user):
    from app.services import risk_service

    f1 = risk_service.flag_user(staff_user.id, "points_abuse")
    f2 = risk_service.flag_user(staff_user.id, "points_abuse")
    assert f1.id == f2.id  # Same flag, not duplicated


def test_has_active_flag(app, staff_user):
    from app.services import risk_service

    assert not risk_service.has_active_flag(staff_user.id)
    risk_service.flag_user(staff_user.id, "spend_abuse")
    assert risk_service.has_active_flag(staff_user.id)
    assert risk_service.has_active_flag(staff_user.id, "spend_abuse")
    assert not risk_service.has_active_flag(staff_user.id, "points_abuse")


def test_clear_flags(app, staff_user):
    from app.models.audit import AuditLog
    from app.services import risk_service

    risk_service.flag_user(staff_user.id, "points_abuse")
    risk_service.flag_user(staff_user.id, "spend_abuse")
    count = risk_service.clear_flags(staff_user.id, actor_id=staff_user.id)
    assert count == 2
    assert not risk_service.has_active_flag(staff_user.id)
    assert AuditLog.query.filter_by(action="risk_flag_cleared").count() == 1


def test_check_points_abuse():
    from app.services.risk_service import check_points_abuse

    assert not check_points_abuse(1, 5)
    assert check_points_abuse(1, 11)


def test_check_spend_abuse():
    from app.services.risk_service import check_spend_abuse

    assert not check_spend_abuse(1, 100.0)
    assert check_spend_abuse(1, 201.0)


def test_risk_api_list_requires_auth(client):
    resp = client.get("/api/risk")
    assert resp.status_code == 401


def test_risk_api_list(client, logged_in_admin, staff_user, app):
    from app.services import risk_service

    risk_service.flag_user(staff_user.id, "points_abuse")
    resp = client.get("/api/risk")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert len(results) == 1
    assert results[0]["type"] == "points_abuse"


def test_risk_api_clear_requires_admin(client, logged_in_staff, staff_user, app):
    from app.services import risk_service

    risk_service.flag_user(staff_user.id, "points_abuse")
    resp = client.post(f"/api/risk/{staff_user.id}/clear", json={})
    assert resp.status_code == 403


def test_risk_api_clear(client, logged_in_admin, staff_user, app):
    from app.services import risk_service

    risk_service.flag_user(staff_user.id, "points_abuse")
    resp = client.post(f"/api/risk/{staff_user.id}/clear", json={})
    assert resp.status_code == 200
    assert resp.get_json()["cleared"] == 1


def test_risk_ui_page(client, logged_in_admin):
    resp = client.get("/risk")
    assert resp.status_code == 200
    assert b"Risk" in resp.data


def test_risk_ui_flag_displayed(client, logged_in_admin, staff_user, app):
    from app.services import risk_service

    risk_service.flag_user(staff_user.id, "spend_abuse")
    resp = client.get("/risk")
    assert b"spend_abuse" in resp.data
    assert b"risk-row" in resp.data


def test_risk_ui_clear_partial(client, logged_in_admin, staff_user, app):
    from app.services import risk_service

    risk_service.flag_user(staff_user.id, "points_abuse")
    resp = client.post(f"/risk/{staff_user.id}/clear")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"no-flags" in resp.data or b"No active" in resp.data


def test_risk_ui_clear_member_partial(client, logged_in_admin, seeded_member, app):
    from app.services import risk_service

    risk_service.flag_member(seeded_member.id, "spend_abuse")
    resp = client.post(f"/risk/member/{seeded_member.id}/clear")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
