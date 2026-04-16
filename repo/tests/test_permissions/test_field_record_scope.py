"""Tests for field-level and record-level ABAC scope enforcement."""


def test_get_restricted_fields_no_scope(app, staff_user):
    """When no field-scope records exist, no fields are restricted."""
    from app.services import permission_service

    restricted = permission_service.get_restricted_fields(
        staff_user, "member", "view"
    )
    assert restricted == set()


def test_get_restricted_fields_with_scope(app, staff_user, admin_user):
    """Field-scope records restrict fields not explicitly granted."""
    from app.services import permission_service

    # Grant staff access to phone_number field only
    permission_service.grant_permission(
        role_name="staff",
        resource="member",
        action="view",
        scope_type="field",
        scope_value="phone_number",
        actor_id=admin_user.id,
    )

    restricted = permission_service.get_restricted_fields(
        staff_user, "member", "view"
    )
    # phone_number is allowed, but stored_value_balance and points_balance are restricted
    assert "phone_number" not in restricted
    assert "stored_value_balance" in restricted
    assert "points_balance" in restricted


def test_get_restricted_fields_admin_sees_all(app, admin_user):
    """Admin users are never restricted regardless of scope records."""
    from app.services import permission_service

    restricted = permission_service.get_restricted_fields(
        admin_user, "member", "view"
    )
    assert restricted == set()


def test_member_to_dict_with_field_restriction(app, staff_user, admin_user, seeded_member):
    """member_to_dict applies field-level masking from ABAC scope."""
    from app.services import member_service, permission_service

    # Grant staff access to phone_number field only (not stored_value_balance)
    permission_service.grant_permission(
        role_name="staff",
        resource="member",
        action="view",
        scope_type="field",
        scope_value="phone_number",
        actor_id=admin_user.id,
    )

    restricted = permission_service.get_restricted_fields(
        staff_user, "member", "view"
    )
    result = member_service.member_to_dict(
        seeded_member, is_admin=False, restricted_fields=restricted,
    )

    # points_balance should be masked
    assert result["points_balance"] == "***"
    # stored_value_balance should be masked
    assert result["stored_value_balance"] == "****"


def test_check_record_access_no_scope(app, staff_user):
    """When no record-scope records exist, access is allowed."""
    from app.services import permission_service

    result = permission_service.check_record_access(
        staff_user, "member", "view", record_id=1,
    )
    assert result is True


def test_check_record_access_with_matching_scope(app, staff_user, admin_user):
    """Record-scope grants access to specific records only."""
    from app.services import permission_service

    permission_service.grant_permission(
        role_name="staff",
        resource="member",
        action="view",
        scope_type="record",
        scope_value="42",
        actor_id=admin_user.id,
    )

    assert permission_service.check_record_access(
        staff_user, "member", "view", record_id=42,
    ) is True

    assert permission_service.check_record_access(
        staff_user, "member", "view", record_id=99,
    ) is False


def test_check_record_access_admin_bypasses(app, admin_user):
    """Admin always has record-level access."""
    from app.services import permission_service

    assert permission_service.check_record_access(
        admin_user, "member", "view", record_id=999,
    ) is True
