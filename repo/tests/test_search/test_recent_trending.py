"""Tests for recent and trending search surfacing in UI and API."""


def test_recent_api_endpoint(client, logged_in_staff, seeded_member):
    """GET /api/search/recent returns the user's recent searches."""
    # Perform some searches
    client.get("/api/search?q=eagle")
    client.get("/api/search?q=lion")

    resp = client.get("/api/search/recent")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert len(results) >= 2
    terms = [r["query"] for r in results]
    assert "lion" in terms
    assert "eagle" in terms


def test_recent_api_scoped_to_user(
    app, client, staff_user, admin_user
):
    """Recent searches are scoped per-user."""
    from app.services import auth_service

    # Staff searches
    client.post("/api/auth/login", json={
        "username": staff_user.username, "password": "pw-staff-123",
    })
    client.get("/api/search?q=staff_query")
    client.post("/api/auth/logout", json={})

    # Admin searches
    client.post("/api/auth/login", json={
        "username": admin_user.username, "password": "pw-admin-123",
    })
    client.get("/api/search?q=admin_query")

    resp = client.get("/api/search/recent")
    results = resp.get_json()["results"]
    terms = [r["query"] for r in results]
    assert "admin_query" in terms
    assert "staff_query" not in terms


def test_suggestions_partial_shows_recent_and_trending(
    client, logged_in_staff, seeded_member
):
    """The /search/suggestions partial renders both recent and trending."""
    # Generate some search history
    client.get(f"/api/search?q={seeded_member.name}")
    client.get(f"/api/search?q={seeded_member.name}")

    resp = client.get("/search/suggestions")
    assert resp.status_code == 200
    html = resp.data.decode()

    assert "search-recent" in html
    assert "search-trending" in html
    assert seeded_member.name.lower() in html


def test_search_page_loads_suggestions_on_load(client, logged_in_staff):
    """search.html includes hx-trigger='load' for suggestions."""
    resp = client.get("/search")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'hx-get="/search/suggestions"' in html
    assert 'hx-trigger="load"' in html


def test_trending_api_returns_sorted(client, logged_in_staff):
    """Trending returns terms sorted by frequency descending."""
    for _ in range(5):
        client.get("/api/search?q=popular_term")
    for _ in range(2):
        client.get("/api/search?q=less_popular")

    resp = client.get("/api/search/trending")
    results = resp.get_json()["results"]
    assert len(results) >= 2
    assert results[0]["query"] == "popular_term"
    assert results[0]["count"] == 5
    assert results[1]["query"] == "less_popular"
    assert results[1]["count"] == 2


def test_recent_scoped_to_device(client, logged_in_staff):
    """Recent searches with X-Device-ID are isolated per device."""
    device_a = "kiosk-alpha"
    device_b = "kiosk-beta"

    client.get("/api/search?q=on_device_a", headers={"X-Device-ID": device_a})
    client.get("/api/search?q=on_device_b", headers={"X-Device-ID": device_b})

    resp_a = client.get("/api/search/recent", headers={"X-Device-ID": device_a})
    terms_a = [r["query"] for r in resp_a.get_json()["results"]]
    assert "on_device_a" in terms_a
    assert "on_device_b" not in terms_a

    resp_b = client.get("/api/search/recent", headers={"X-Device-ID": device_b})
    terms_b = [r["query"] for r in resp_b.get_json()["results"]]
    assert "on_device_b" in terms_b
    assert "on_device_a" not in terms_b


def test_trending_scoped_to_device(client, logged_in_staff):
    """Trending with X-Device-ID reflects only that device's search history."""
    device_a = "kiosk-alpha-trend"
    device_b = "kiosk-beta-trend"

    for _ in range(4):
        client.get("/api/search?q=alpha_term", headers={"X-Device-ID": device_a})
    for _ in range(6):
        client.get("/api/search?q=beta_term", headers={"X-Device-ID": device_b})

    resp_a = client.get("/api/search/trending", headers={"X-Device-ID": device_a})
    terms_a = [r["query"] for r in resp_a.get_json()["results"]]
    assert "alpha_term" in terms_a
    assert "beta_term" not in terms_a

    resp_b = client.get("/api/search/trending", headers={"X-Device-ID": device_b})
    terms_b = [r["query"] for r in resp_b.get_json()["results"]]
    assert "beta_term" in terms_b
    assert "alpha_term" not in terms_b
