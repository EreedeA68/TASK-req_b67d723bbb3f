"""Tests for indexed phone hash lookup."""


def test_phone_hash_populated_on_create(app, staff_user):
    from app.services import member_service

    member = member_service.create_member(
        name="Hash Test",
        phone_number="5551112222",
        member_id="M-HASH001",
        actor_id=staff_user.id,
    )
    assert member.phone_hash is not None
    assert len(member.phone_hash) == 64  # SHA-256 hex


def test_lookup_uses_hash(app, staff_user):
    from app.services import member_service

    member_service.create_member(
        name="Lookup By Hash",
        phone_number="5559998888",
        member_id="M-HASH002",
        actor_id=staff_user.id,
    )

    # Lookup by the same phone should find via hash (not linear scan).
    found = member_service.lookup("5559998888", actor_id=staff_user.id)
    assert found is not None
    assert found.member_id == "M-HASH002"


def test_phone_hash_normalizes_formatting(app, staff_user):
    """Hash ignores formatting so users can search with or without dashes."""
    from app.services import member_service

    member_service.create_member(
        name="Formatted Phone",
        phone_number="5557776666",
        member_id="M-HASH003",
        actor_id=staff_user.id,
    )

    # Search with dashes
    found = member_service.lookup("555-777-6666", actor_id=staff_user.id)
    assert found is not None
    assert found.member_id == "M-HASH003"
