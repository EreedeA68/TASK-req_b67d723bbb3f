"""Stored-value ledger tests — credit, debit, insufficient balance, risk check, balance."""
import pytest

from app.services import stored_value_service
from app.services.stored_value_service import StoredValueError


def test_credit_adds_balance(app, seeded_member, staff_user):
    entry = stored_value_service.credit(
        member_id=seeded_member.id,
        amount=100.0,
        description="initial load",
        actor_id=staff_user.id,
    )
    assert entry.type == "credit"
    assert entry.amount == 100.0
    assert entry.description == "initial load"

    balance = stored_value_service.get_balance(seeded_member.id)
    assert balance == 100.0


def test_debit_reduces_balance(app, seeded_member, staff_user):
    stored_value_service.credit(
        member_id=seeded_member.id,
        amount=100.0,
        actor_id=staff_user.id,
    )
    entry = stored_value_service.debit(
        member_id=seeded_member.id,
        amount=30.0,
        actor_id=staff_user.id,
    )
    assert entry.type == "debit"
    assert entry.amount == 30.0

    balance = stored_value_service.get_balance(seeded_member.id)
    assert balance == 70.0


def test_debit_insufficient_balance(app, seeded_member, staff_user):
    stored_value_service.credit(
        member_id=seeded_member.id,
        amount=50.0,
        actor_id=staff_user.id,
    )
    with pytest.raises(StoredValueError, match="insufficient"):
        stored_value_service.debit(
            member_id=seeded_member.id,
            amount=100.0,
            actor_id=staff_user.id,
        )


def test_debit_blocked_by_risk_flag(app, seeded_member, staff_user):
    from app.services import risk_service

    stored_value_service.credit(
        member_id=seeded_member.id,
        amount=500.0,
        actor_id=staff_user.id,
    )

    # Flag the member for spend abuse
    risk_service.flag_member(seeded_member.id, "spend_abuse", actor_id=staff_user.id)

    with pytest.raises(StoredValueError, match="risk flag"):
        stored_value_service.debit(
            member_id=seeded_member.id,
            amount=10.0,
            actor_id=staff_user.id,
        )


def test_risk_flag_triggered_over_200_daily(app, seeded_member, staff_user):
    from app.models.risk import RiskFlag

    stored_value_service.credit(
        member_id=seeded_member.id,
        amount=500.0,
        actor_id=staff_user.id,
    )

    # Debit $201 in a single day to trigger risk flag
    stored_value_service.debit(
        member_id=seeded_member.id,
        amount=201.0,
        actor_id=staff_user.id,
    )

    flag = RiskFlag.query.filter_by(
        member_id=seeded_member.id, type="spend_abuse", active=True
    ).first()
    assert flag is not None


def test_balance_calculation_from_ledger(app, seeded_member, staff_user):
    stored_value_service.credit(
        member_id=seeded_member.id,
        amount=200.0,
        actor_id=staff_user.id,
    )
    stored_value_service.credit(
        member_id=seeded_member.id,
        amount=50.0,
        description="bonus",
        actor_id=staff_user.id,
    )
    stored_value_service.debit(
        member_id=seeded_member.id,
        amount=75.0,
        actor_id=staff_user.id,
    )

    balance = stored_value_service.get_balance(seeded_member.id)
    assert balance == 175.0


def test_get_history(app, seeded_member, staff_user):
    stored_value_service.credit(
        member_id=seeded_member.id,
        amount=100.0,
        actor_id=staff_user.id,
    )
    stored_value_service.debit(
        member_id=seeded_member.id,
        amount=25.0,
        actor_id=staff_user.id,
    )

    history = stored_value_service.get_history(seeded_member.id)
    assert len(history) == 2
    # Newest first
    assert history[0].type == "debit"
    assert history[1].type == "credit"


def test_credit_zero_amount_rejected(app, seeded_member, staff_user):
    with pytest.raises(StoredValueError, match="positive"):
        stored_value_service.credit(
            member_id=seeded_member.id,
            amount=0,
            actor_id=staff_user.id,
        )


def test_debit_zero_amount_rejected(app, seeded_member, staff_user):
    with pytest.raises(StoredValueError, match="positive"):
        stored_value_service.debit(
            member_id=seeded_member.id,
            amount=0,
            actor_id=staff_user.id,
        )


def test_credit_nonexistent_member(app, staff_user):
    with pytest.raises(StoredValueError, match="member not found"):
        stored_value_service.credit(
            member_id=99999,
            amount=10.0,
            actor_id=staff_user.id,
        )


def test_api_credit(client, logged_in_staff, seeded_member):
    resp = client.post("/api/stored-value/credit", json={
        "member_id": seeded_member.id,
        "amount": 50.0,
        "description": "test credit",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["type"] == "credit"
    assert data["amount"] == 50.0


def test_api_debit(client, logged_in_staff, seeded_member):
    client.post("/api/stored-value/credit", json={
        "member_id": seeded_member.id,
        "amount": 100.0,
    })
    resp = client.post("/api/stored-value/debit", json={
        "member_id": seeded_member.id,
        "amount": 30.0,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["type"] == "debit"
    assert data["amount"] == 30.0


def test_api_balance(client, logged_in_staff, seeded_member):
    """Staff sees masked balance by default (field-scope grant required for raw)."""
    client.post("/api/stored-value/credit", json={
        "member_id": seeded_member.id,
        "amount": 100.0,
    })
    resp = client.get(f"/api/stored-value/balance/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["balance"] == "****"


def test_api_history(client, logged_in_staff, seeded_member):
    client.post("/api/stored-value/credit", json={
        "member_id": seeded_member.id,
        "amount": 100.0,
    })
    resp = client.get(f"/api/stored-value/history/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["results"]) == 1


def test_api_requires_auth(client):
    resp = client.post("/api/stored-value/credit", json={
        "member_id": 1,
        "amount": 10.0,
    })
    assert resp.status_code == 401
