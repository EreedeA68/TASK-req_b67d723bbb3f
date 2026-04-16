"""Booking HTMX view tests — covers form-create, confirm, cancel, and list partial."""
from datetime import datetime, timedelta


def _start_end(days=2):
    start = datetime.utcnow().replace(microsecond=0) + timedelta(days=days)
    return start, start + timedelta(hours=1)


def _login(client, user, password):
    client.post("/api/auth/logout", json={})
    client.post("/api/auth/login", json={"username": user.username, "password": password})


# ── Page load ──────────────────────────────────────────────────────────────

def test_bookings_page_renders(client, logged_in_staff):
    resp = client.get("/bookings")
    assert resp.status_code == 200
    assert b"booking" in resp.data.lower()


# ── Create — success ───────────────────────────────────────────────────────

def test_bookings_create_success(
    client, logged_in_staff, seeded_member, photographer_user, app
):
    start, end = _start_end()
    resp = client.post("/bookings/create", data={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 200
    assert b"booking" in resp.data.lower()


# ── Create — error path (bad input) ───────────────────────────────────────

def test_bookings_create_missing_fields_returns_400(client, logged_in_staff):
    resp = client.post("/bookings/create", data={})
    assert resp.status_code == 400


def test_bookings_create_conflict_returns_400(
    client, logged_in_staff, seeded_member, photographer_user
):
    start, end = _start_end()
    # First booking succeeds
    client.post("/bookings/create", data={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    # Overlapping booking should fail with 400 and show error
    resp = client.post("/bookings/create", data={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert resp.status_code == 400


# ── Confirm ────────────────────────────────────────────────────────────────

def _make_booking(client, seeded_member, photographer_user):
    start, end = _start_end(days=3)
    r = client.post("/api/bookings", json={
        "member_id": seeded_member.id,
        "photographer_id": photographer_user.id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    })
    assert r.status_code == 201
    return r.get_json()["id"]


def test_bookings_confirm_not_found(client, logged_in_staff):
    resp = client.post("/bookings/9999/confirm")
    assert resp.status_code == 404


def test_bookings_confirm_success(
    client, logged_in_staff, seeded_member, photographer_user
):
    booking_id = _make_booking(client, seeded_member, photographer_user)
    resp = client.post(f"/bookings/{booking_id}/confirm")
    assert resp.status_code == 200


# ── Cancel ─────────────────────────────────────────────────────────────────

def test_bookings_cancel_not_found(client, logged_in_staff):
    resp = client.post("/bookings/9999/cancel")
    assert resp.status_code == 404


def test_bookings_cancel_success(
    client, logged_in_staff, seeded_member, photographer_user
):
    booking_id = _make_booking(client, seeded_member, photographer_user)
    resp = client.post(f"/bookings/{booking_id}/cancel")
    assert resp.status_code == 200


def test_bookings_cancel_already_cancelled_returns_400(
    client, logged_in_staff, seeded_member, photographer_user
):
    booking_id = _make_booking(client, seeded_member, photographer_user)
    client.post(f"/bookings/{booking_id}/cancel")
    # Second cancel on an already-cancelled booking should fail
    resp = client.post(f"/bookings/{booking_id}/cancel")
    assert resp.status_code == 400


# ── List partial ───────────────────────────────────────────────────────────

def test_bookings_list_partial(client, logged_in_staff):
    resp = client.get("/bookings/list")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
