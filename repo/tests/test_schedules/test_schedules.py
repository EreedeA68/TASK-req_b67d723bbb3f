"""Photographer schedule tests — API, overlap rejection, audit."""


def test_create_schedule_requires_auth(client, photographer_user):
    resp = client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
    })
    assert resp.status_code == 401


def test_create_schedule_success(client, logged_in_staff, photographer_user, app):
    from app.models.audit import AuditLog
    from app.models.schedule import PhotographerSchedule

    resp = client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
        "type": "working",
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["photographer_id"] == photographer_user.id
    assert data["date"] == "2026-05-01"
    assert data["type"] == "working"
    # DB
    assert PhotographerSchedule.query.count() == 1
    # Audit
    assert AuditLog.query.filter_by(action="schedule_created").count() == 1


def test_create_schedule_overlap_rejected(
    client, logged_in_staff, photographer_user, app
):
    from app.models.audit import AuditLog

    payload = {
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
    }
    client.post("/api/schedules", json=payload)
    # Second, overlapping
    resp = client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "11:00",
        "end_time": "14:00",
    })
    assert resp.status_code == 400
    assert "overlap" in resp.get_json()["error"].lower()
    assert AuditLog.query.filter_by(action="schedule_overlap_rejected").count() == 1


def test_create_schedule_no_overlap_different_day(
    client, logged_in_staff, photographer_user
):
    client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
    })
    resp = client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-02",
        "start_time": "09:00",
        "end_time": "12:00",
    })
    assert resp.status_code == 201


def test_create_schedule_end_before_start_rejected(
    client, logged_in_staff, photographer_user
):
    resp = client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "14:00",
        "end_time": "09:00",
    })
    assert resp.status_code == 400


def test_create_schedule_invalid_type_rejected(
    client, logged_in_staff, photographer_user
):
    resp = client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
        "type": "vacation",
    })
    assert resp.status_code == 400


def test_list_schedules(client, logged_in_staff, photographer_user):
    client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
    })
    resp = client.get("/api/schedules")
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) == 1


def test_list_schedules_filtered_by_date(
    client, logged_in_staff, photographer_user
):
    client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
    })
    client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-02",
        "start_time": "09:00",
        "end_time": "12:00",
    })
    resp = client.get("/api/schedules?date=2026-05-01")
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) == 1


def test_schedule_ui_page(client, logged_in_staff):
    resp = client.get("/schedules")
    assert resp.status_code == 200
    assert b"Photographer Schedules" in resp.data


def test_schedule_ui_list_partial(client, logged_in_staff, photographer_user):
    client.post("/api/schedules", json={
        "photographer_id": photographer_user.id,
        "date": "2026-05-01",
        "start_time": "09:00",
        "end_time": "12:00",
    })
    resp = client.get("/schedules/list")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"schedule-row" in resp.data
