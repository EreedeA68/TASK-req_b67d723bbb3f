"""Schedule HTMX view tests — create form success/error, list partial."""
from datetime import date, timedelta


def _tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()


def test_schedules_page_renders(client, logged_in_staff):
    resp = client.get("/schedules")
    assert resp.status_code == 200
    assert b"schedule" in resp.data.lower()


def test_schedules_create_success(client, logged_in_staff, photographer_user):
    resp = client.post("/schedules/create", data={
        "photographer_id": photographer_user.id,
        "date": _tomorrow(),
        "start_time": "09:00",
        "end_time": "17:00",
        "type": "working",
    })
    assert resp.status_code == 200
    assert b"schedule" in resp.data.lower()


def test_schedules_create_missing_fields_returns_400(client, logged_in_staff):
    resp = client.post("/schedules/create", data={})
    assert resp.status_code == 400


def test_schedules_create_invalid_time_returns_400(client, logged_in_staff, photographer_user):
    resp = client.post("/schedules/create", data={
        "photographer_id": photographer_user.id,
        "date": _tomorrow(),
        "start_time": "not-a-time",
        "end_time": "17:00",
        "type": "working",
    })
    assert resp.status_code == 400


def test_schedules_list_partial(client, logged_in_staff):
    resp = client.get("/schedules/list")
    assert resp.status_code == 200
    assert b"<html" not in resp.data


def test_schedules_list_partial_with_filters(client, logged_in_staff, photographer_user):
    resp = client.get(f"/schedules/list?photographer_id={photographer_user.id}&date={_tomorrow()}")
    assert resp.status_code == 200
