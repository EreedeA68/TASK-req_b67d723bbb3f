"""Export visibility and CSV content are actor-scoped — non-admin sees only own data."""
import csv
import io


def _login(client, username, password):
    client.post("/api/auth/logout", json={})
    resp = client.post("/api/auth/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200


def test_non_admin_sees_only_own_exports(
    app, client, staff_user, admin_user
):
    """Staff A cannot see exports created by admin or other staff."""
    from app.services import auth_service

    # Admin creates an export
    _login(client, admin_user.username, "pw-admin-123")
    r = client.post("/api/exports", json={"type": "members"})
    assert r.status_code == 201

    # Staff creates their own export
    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/exports", json={"type": "orders"})
    assert r.status_code == 201
    my_export_id = r.get_json()["id"]

    resp = client.get("/api/exports")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    ids = [j["id"] for j in results]
    # Staff only sees own
    assert my_export_id in ids
    assert len(ids) == 1
    # Admin's export is NOT visible
    for j in results:
        assert j["user_id"] == staff_user.id


def _read_csv_ids(filepath: str) -> list[str]:
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row["id"] for row in reader]


def _seed_member_id(app, actor_id, name="Export Test Member", phone="5550000099", mid="M-EXP001"):
    from app.services import member_service
    with app.app_context():
        m = member_service.create_member(
            name=name, phone_number=phone, member_id=mid, actor_id=actor_id,
        )
        return m.id


def test_orders_export_scope_non_admin(app, client, staff_user, admin_user):
    """Non-admin orders export only includes rows the actor created."""
    from app.services import order_service

    member_id = _seed_member_id(app, admin_user.id)

    with app.app_context():
        order_admin_id = order_service.create_order(
            member_id, actor_id=admin_user.id, subtotal=10.0
        ).id
        order_staff_id = order_service.create_order(
            member_id, actor_id=staff_user.id, subtotal=20.0
        ).id

    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/exports", json={"type": "orders"})
    assert r.status_code == 201
    filepath = r.get_json()["file_path"]

    with app.app_context():
        ids = _read_csv_ids(filepath)

    assert str(order_staff_id) in ids
    assert str(order_admin_id) not in ids, "non-admin export must not include other users' orders"


def test_bookings_export_scope_non_admin(app, client, staff_user, admin_user, photographer_user):
    """Non-admin bookings export only includes rows the actor created or is assigned to."""
    from datetime import datetime, timedelta
    from app.services import booking_service

    member_id = _seed_member_id(app, admin_user.id)

    with app.app_context():
        start = datetime.utcnow().replace(microsecond=0) + timedelta(days=2)
        end = start + timedelta(hours=1)
        start2 = start + timedelta(hours=2)
        end2 = start2 + timedelta(hours=1)

        # Booking created by staff (staff is creator)
        booking_staff_id = booking_service.create_booking(
            member_id=member_id, photographer_id=photographer_user.id,
            start_time=start, end_time=end, actor_id=staff_user.id,
        ).id
        # Booking created by admin only — staff has no relation to it
        booking_admin_id = booking_service.create_booking(
            member_id=member_id, photographer_id=photographer_user.id,
            start_time=start2, end_time=end2, actor_id=admin_user.id,
        ).id

    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/exports", json={"type": "bookings"})
    assert r.status_code == 201
    filepath = r.get_json()["file_path"]

    with app.app_context():
        ids = _read_csv_ids(filepath)

    assert str(booking_staff_id) in ids
    assert str(booking_admin_id) not in ids, "non-admin export must not include unrelated bookings"


def test_orders_export_admin_sees_all(app, client, staff_user, admin_user):
    """Admin orders export includes rows created by any user."""
    from app.services import order_service

    member_id = _seed_member_id(app, admin_user.id)

    with app.app_context():
        order_staff_id = order_service.create_order(
            member_id, actor_id=staff_user.id, subtotal=5.0
        ).id

    _login(client, admin_user.username, "pw-admin-123")
    r = client.post("/api/exports", json={"type": "orders"})
    assert r.status_code == 201
    filepath = r.get_json()["file_path"]

    with app.app_context():
        ids = _read_csv_ids(filepath)

    assert str(order_staff_id) in ids


def test_members_export_scope_non_admin(app, client, staff_user, admin_user, photographer_user):
    """Non-admin members export only includes members the actor has served."""
    from app.services import member_service, order_service

    with app.app_context():
        member_served = member_service.create_member(
            name="Served Member", phone_number="5550000011", member_id="M-EXP011",
            actor_id=admin_user.id,
        )
        member_unserved = member_service.create_member(
            name="Unserved Member", phone_number="5550000012", member_id="M-EXP012",
            actor_id=admin_user.id,
        )
        served_id = member_served.id
        unserved_id = member_unserved.id
        # Staff creates an order for member_served only
        order_service.create_order(served_id, actor_id=staff_user.id, subtotal=10.0)

    _login(client, staff_user.username, "pw-staff-123")
    r = client.post("/api/exports", json={"type": "members"})
    assert r.status_code == 201
    filepath = r.get_json()["file_path"]

    with app.app_context():
        ids = _read_csv_ids(filepath)

    assert str(served_id) in ids
    assert str(unserved_id) not in ids, "non-admin export must not include members with no actor interaction"


def test_admin_sees_all_exports(app, client, staff_user, admin_user):
    """Admin sees exports from any user."""
    # Staff creates one
    _login(client, staff_user.username, "pw-staff-123")
    client.post("/api/exports", json={"type": "orders"})

    # Admin creates one
    _login(client, admin_user.username, "pw-admin-123")
    client.post("/api/exports", json={"type": "members"})

    resp = client.get("/api/exports")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    user_ids = {j["user_id"] for j in results}
    assert staff_user.id in user_ids
    assert admin_user.id in user_ids
