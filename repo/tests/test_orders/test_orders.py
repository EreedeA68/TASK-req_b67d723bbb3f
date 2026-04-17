"""Order API + state machine tests."""
import pytest

from app.core.state_machine import (
    FINAL_STATES,
    InvalidTransitionError,
    can_transition,
    next_status,
    validate_transition,
)


def test_state_machine_valid_transitions():
    assert can_transition("created", "paid")
    assert can_transition("paid", "in_prep")
    assert can_transition("in_prep", "ready")
    assert can_transition("ready", "delivered")
    assert can_transition("delivered", "reviewed")


def test_state_machine_invalid_transitions():
    assert not can_transition("created", "ready")
    assert not can_transition("paid", "reviewed")
    assert not can_transition("reviewed", "created")


def test_state_machine_self_transitions_invalid():
    for state in ["created", "paid", "in_prep", "ready", "delivered", "reviewed"]:
        assert not can_transition(state, state), f"{state}->{state} must be invalid"


def test_validate_transition_raises():
    with pytest.raises(InvalidTransitionError):
        validate_transition("created", "delivered")


def test_next_status_at_end_raises():
    with pytest.raises(InvalidTransitionError):
        next_status("reviewed")


def test_final_states_exposed():
    assert "reviewed" in FINAL_STATES


def test_create_order_requires_auth(client, seeded_member, app):
    from app.models.audit import AuditLog

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication required"
    unauth = AuditLog.query.filter_by(action="unauthorized_access").count()
    assert unauth == 1


def test_create_order_success(client, logged_in_staff, seeded_member, app):
    from app.models.order import Order, OrderEvent

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 100.0, "discount": 5.0},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "created"
    assert data["subtotal"] == 100.0
    assert data["discount"] == 5.0
    assert data["total"] == 95.0
    # DB state
    from app.db import db as _db

    order = _db.session.get(Order, data["id"])
    assert order is not None
    assert order.status == "created"
    # OrderEvent for 'created' is recorded
    events = OrderEvent.query.filter_by(order_id=order.id).all()
    assert [e.status for e in events] == ["created"]


def test_create_order_unknown_member(client, logged_in_staff):
    resp = client.post(
        "/api/orders",
        json={"member_id": 99999, "subtotal": 10.0},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "member not found"


def test_create_order_negative_subtotal_rejected(
    client, logged_in_staff, seeded_member
):
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": -1.0},
    )
    assert resp.status_code == 400
    assert ">= 0" in resp.get_json()["error"] or "must be" in resp.get_json()["error"]


def test_create_order_missing_subtotal_rejected(
    client, logged_in_staff, seeded_member
):
    resp = client.post("/api/orders", json={"member_id": seeded_member.id})
    assert resp.status_code == 400
    assert "subtotal" in resp.get_json()["error"]


def test_create_order_missing_member_id_rejected(client, logged_in_staff):
    resp = client.post("/api/orders", json={"subtotal": 10.0})
    assert resp.status_code == 400


def test_create_order_discount_cannot_exceed_subtotal(
    client, logged_in_staff, seeded_member
):
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 5.0, "discount": 10.0},
    )
    assert resp.status_code == 400


def test_pay_order_transitions_status(client, logged_in_staff, seeded_member, app):
    from app.models.order import Order, OrderEvent

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]
    resp = client.post(f"/api/orders/{order_id}/pay", json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "paid"
    # DB state reflects transition
    from app.db import db as _db

    order = _db.session.get(Order, order_id)
    assert order.status == "paid"
    # Both events present
    statuses = [e.status for e in OrderEvent.query.filter_by(order_id=order_id).all()]
    assert statuses == ["created", "paid"]


def test_invalid_transition_rejected(client, logged_in_staff, seeded_member, app):
    from app.models.audit import AuditLog
    from app.services.order_service import OrderError, get_by_id, transition

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]
    order = get_by_id(order_id)
    with pytest.raises(OrderError):
        transition(order, "ready")
    rejections = AuditLog.query.filter_by(action="order_transition_rejected").all()
    assert len(rejections) == 1
    md = rejections[0].get_metadata()
    assert md["from"] == "created"
    assert md["to"] == "ready"
    assert md["reason"] == "invalid"


def test_duplicate_transition_rejected(client, logged_in_staff, seeded_member, app):
    """Transitioning to the current state must be rejected as a duplicate."""
    from app.models.audit import AuditLog
    from app.services.order_service import OrderError, get_by_id, transition

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order = get_by_id(resp.get_json()["id"])
    with pytest.raises(OrderError) as exc:
        transition(order, "created")
    assert "duplicate" in str(exc.value).lower() or "already" in str(exc.value).lower()
    rejections = AuditLog.query.filter_by(action="order_transition_rejected").all()
    assert rejections[-1].get_metadata()["reason"] == "duplicate"


def test_transition_from_final_state_rejected(
    client, logged_in_staff, seeded_member, app
):
    """Once an order is 'reviewed', no further transitions are allowed."""
    from app.models.audit import AuditLog
    from app.services.order_service import OrderError, advance, get_by_id, transition

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    for _ in range(4):
        client.post(f"/api/orders/{order_id}/advance", json={})
    order = get_by_id(order_id)
    assert order.status == "reviewed"

    # Advance rejected
    with pytest.raises(OrderError):
        advance(order)
    # Explicit transition rejected
    with pytest.raises(OrderError):
        transition(order, "created")
    rejections = AuditLog.query.filter_by(action="order_transition_rejected").all()
    reasons = {r.get_metadata().get("reason") for r in rejections}
    assert "final_state" in reasons


def test_full_order_lifecycle(client, logged_in_staff, seeded_member, app):
    from app.models.order import Order, OrderEvent

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]

    r = client.post(f"/api/orders/{order_id}/pay", json={})
    assert r.get_json()["status"] == "paid"

    for expected in ["in_prep", "ready", "delivered", "reviewed"]:
        r = client.post(f"/api/orders/{order_id}/advance", json={})
        assert r.status_code == 200
        assert r.get_json()["status"] == expected

    # Advancing past "reviewed" fails
    r = client.post(f"/api/orders/{order_id}/advance", json={})
    assert r.status_code == 400
    assert "final" in r.get_json()["error"].lower()

    # DB should have 6 events, in order
    statuses = [
        e.status
        for e in OrderEvent.query.filter_by(order_id=order_id)
        .order_by(OrderEvent.timestamp)
        .all()
    ]
    assert statuses == [
        "created",
        "paid",
        "in_prep",
        "ready",
        "delivered",
        "reviewed",
    ]
    from app.db import db as _db

    assert _db.session.get(Order, order_id).status == "reviewed"


def test_pay_already_paid_rejected_as_duplicate(
    client, logged_in_staff, seeded_member
):
    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    # Pay again — duplicate transition
    r = client.post(f"/api/orders/{order_id}/pay", json={})
    assert r.status_code == 400
    err = r.get_json()["error"].lower()
    assert "duplicate" in err or "already" in err


def test_order_events_are_recorded(app, client, logged_in_staff, seeded_member):
    from app.models.order import OrderEvent

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    events = (
        OrderEvent.query.filter_by(order_id=order_id)
        .order_by(OrderEvent.timestamp)
        .all()
    )
    statuses = [e.status for e in events]
    assert statuses == ["created", "paid"]


def test_order_audit_logged(app, client, logged_in_staff, seeded_member):
    from app.models.audit import AuditLog

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = resp.get_json()["id"]
    entries = AuditLog.query.filter_by(action="order_created").all()
    assert len(entries) == 1
    assert entries[0].get_metadata()["total"] == 10.0
    assert entries[0].resource == f"order:{order_id}"


def test_order_not_found_pay_returns_404(client, logged_in_staff):
    resp = client.post("/api/orders/99999/pay", json={})
    assert resp.status_code == 404


def test_order_not_found_advance_returns_404(client, logged_in_staff):
    resp = client.post("/api/orders/99999/advance", json={})
    assert resp.status_code == 404


def test_kitchen_cannot_create_order(client, logged_in_kitchen, seeded_member, app):
    """Kitchen role cannot create — permission denied + audit."""
    from app.models.audit import AuditLog

    resp = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"
    denials = AuditLog.query.filter_by(action="permission_denied").all()
    assert len(denials) >= 1


def test_create_order_invalid_member_id_type_returns_400(client, logged_in_staff):
    resp = client.post("/api/orders", json={"member_id": "abc", "subtotal": 10.0})
    assert resp.status_code == 400
    assert "member_id" in resp.get_json()["error"]


def test_get_order_not_found_returns_404(client, logged_in_staff):
    resp = client.get("/api/orders/99999")
    assert resp.status_code == 404


def test_get_receipt_not_found_returns_404(client, logged_in_staff):
    resp = client.get("/api/orders/99999/receipt")
    assert resp.status_code == 404


def test_get_print_receipt_not_found_returns_404(client, logged_in_staff):
    resp = client.get("/api/orders/99999/receipt/print")
    assert resp.status_code == 404


def test_pay_order_invalid_redeem_points_type_ignored(
    client, logged_in_staff, seeded_member
):
    resp = client.post(
        "/api/orders", json={"member_id": seeded_member.id, "subtotal": 10.0}
    )
    order_id = resp.get_json()["id"]
    resp = client.post(
        f"/api/orders/{order_id}/pay", json={"redeem_points": "notanint"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "paid"


def test_kitchen_can_advance_order(client, logged_in_staff, seeded_member, app):
    """Kitchen has 'advance' permission — confirm cross-role flow."""
    from app.services import auth_service

    # Staff creates & pays
    r = client.post(
        "/api/orders",
        json={"member_id": seeded_member.id, "subtotal": 10.0},
    )
    order_id = r.get_json()["id"]
    client.post(f"/api/orders/{order_id}/pay", json={})
    # Log out staff, log in kitchen
    client.post("/api/auth/logout", json={})
    auth_service.register("k2", "k2-pw-1", roles=["kitchen"])
    client.post("/api/auth/login", json={"username": "k2", "password": "k2-pw-1"})
    r = client.post(f"/api/orders/{order_id}/advance", json={})
    assert r.status_code == 200
    assert r.get_json()["status"] == "in_prep"
