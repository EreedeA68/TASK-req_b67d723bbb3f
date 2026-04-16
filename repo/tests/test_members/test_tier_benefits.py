"""Tier benefits surfacing in member API and tier lookup API."""


def test_tiers_api_lists_default_tiers(client, logged_in_staff):
    resp = client.get("/api/tiers")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    names = [t["tier_name"] for t in results]
    assert {"standard", "silver", "gold", "platinum"}.issubset(set(names))
    # Each tier has benefits populated
    for t in results:
        assert "benefits" in t
        assert isinstance(t["benefits"], list)


def test_tier_lookup_returns_benefits(client, logged_in_staff):
    resp = client.get("/api/tiers/gold")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["tier_name"] == "gold"
    assert data["max_discount_pct"] == 0.15
    assert len(data["benefits"]) > 0
    assert any("Gold" in b or "gold" in b.lower() for b in data["benefits"])


def test_tier_lookup_not_found(client, logged_in_staff):
    resp = client.get("/api/tiers/mythic")
    assert resp.status_code == 404


def test_member_serializer_includes_tier_benefits(
    app, client, logged_in_staff, seeded_member
):
    """Member API response includes tier_benefits for UX surfacing."""
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "tier_benefits" in data
    assert isinstance(data["tier_benefits"], list)
    assert "tier_description" in data
    assert "tier_max_discount_pct" in data


def test_member_lookup_ui_renders_tier_benefits(
    app, client, logged_in_staff, seeded_member
):
    resp = client.get(f"/members/lookup?q={seeded_member.member_id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "tier-benefits" in html
    # Standard tier benefits include "Points on every purchase"
    assert "Points on every purchase" in html
