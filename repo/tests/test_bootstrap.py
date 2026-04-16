"""Tests for app/__init__.py bootstrap paths — index route, CLI commands, seed logic."""
import pytest


def test_index_redirects_to_members(client, logged_in_staff):
    resp = client.get("/")
    assert resp.status_code in (301, 302)
    assert "members" in resp.headers["Location"]


def test_index_unauthenticated_redirects(client):
    resp = client.get("/")
    # Unauthenticated: redirected (to login) or to members (then to login)
    assert resp.status_code in (301, 302)


def test_check_expiry_cli_command(app):
    """The check-expiry Flask CLI command should run without error."""
    runner = app.test_cli_runner()
    result = runner.invoke(args=["check-expiry"])
    assert result.exit_code == 0
    assert "Expiry sweep complete" in result.output


def test_seed_default_roles_idempotent(app):
    """Calling _seed_default_roles twice should not raise or duplicate roles."""
    from app.models.role import Role
    from app import _seed_default_roles

    with app.app_context():
        count_before = Role.query.count()
        _seed_default_roles()
        _seed_default_roles()
        count_after = Role.query.count()
        assert count_after == count_before


def test_seed_updates_empty_tier_benefits(app):
    """TierRule rows with missing benefits/description get them filled in."""
    from app.db import db
    from app.models.tier_rule import TierRule
    from app import _seed_default_roles

    with app.app_context():
        # Blank out benefits and description on an existing tier
        rule = TierRule.query.filter_by(tier_name="standard").first()
        if rule:
            rule.benefits = ""
            rule.description = ""
            db.session.commit()
            _seed_default_roles()
            db.session.refresh(rule)
            assert rule.benefits != ""
            assert rule.description != ""
