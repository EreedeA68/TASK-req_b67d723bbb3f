"""Search tests — keyword, trending, audit, UI."""


def test_search_requires_auth(client):
    resp = client.get("/api/search?q=test")
    assert resp.status_code == 401


def test_search_empty_query_rejected(client, logged_in_staff):
    resp = client.get("/api/search?q=")
    assert resp.status_code == 400


def test_search_finds_member(client, logged_in_staff, seeded_member, app):
    from app.models.audit import AuditLog

    resp = client.get(f"/api/search?q={seeded_member.name}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["members"]) >= 1
    assert data["members"][0]["name"] == seeded_member.name
    # Audit
    assert AuditLog.query.filter_by(action="search_performed").count() == 1


def test_search_finds_order_by_status(
    client, logged_in_staff, seeded_member, app
):
    client.post("/api/orders", json={
        "member_id": seeded_member.id, "subtotal": 10.0,
    })
    resp = client.get("/api/search?q=created")
    assert resp.status_code == 200
    assert len(resp.get_json()["orders"]) >= 1


def test_search_case_insensitive(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/search?q={seeded_member.name.upper()}")
    assert resp.status_code == 200
    assert len(resp.get_json()["members"]) >= 1


def test_search_no_results(client, logged_in_staff):
    resp = client.get("/api/search?q=ZZZZZZZ")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["members"] == []
    assert data["orders"] == []


def test_trending_updated(client, logged_in_staff, seeded_member, app):
    from app.models.search import SearchTrend

    client.get(f"/api/search?q={seeded_member.name}")
    client.get(f"/api/search?q={seeded_member.name}")
    trend = SearchTrend.query.filter_by(
        term=seeded_member.name.lower()
    ).first()
    assert trend is not None
    assert trend.count == 2


def test_trending_endpoint(client, logged_in_staff, seeded_member):
    client.get("/api/search?q=popular")
    client.get("/api/search?q=popular")
    client.get("/api/search?q=popular")
    resp = client.get("/api/search/trending")
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert len(results) >= 1
    assert results[0]["query"] == "popular"
    assert results[0]["count"] == 3


def test_trending_requires_staff_role(client, logged_in_kitchen):
    resp = client.get("/api/search/trending")
    assert resp.status_code == 403


def test_search_ui_page(client, logged_in_staff):
    resp = client.get("/search")
    assert resp.status_code == 200
    assert b"Search" in resp.data
    assert b"hx-get" in resp.data


def test_search_results_partial_empty(client, logged_in_staff):
    resp = client.get("/search/results?q=")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"Start typing" in resp.data


def test_search_results_partial_with_results(
    client, logged_in_staff, seeded_member
):
    resp = client.get(f"/search/results?q={seeded_member.name}")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert seeded_member.name.encode() in resp.data
    assert b"search-members" in resp.data


def test_search_results_partial_no_matches(client, logged_in_staff):
    resp = client.get("/search/results?q=ZZZZZNOTFOUND")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
    assert b"No results" in resp.data


def test_search_results_partial_service_error_returns_empty(client, logged_in_staff):
    from unittest.mock import patch
    from app.services.search_service import SearchError

    with patch("app.views.search.search_service.perform_search", side_effect=SearchError("oops")):
        resp = client.get("/search/results?q=tiger")
    assert resp.status_code == 200
    assert b"<html" not in resp.data
