"""Versions HTMX view tests — snapshot form, error paths."""


def test_versions_page_renders(client, logged_in_admin):
    resp = client.get("/versions")
    assert resp.status_code == 200
    assert b"version" in resp.data.lower()


def test_versions_snapshot_invalid_entity_id(client, logged_in_admin):
    resp = client.post("/versions/snapshot", data={
        "entity_type": "member",
        "entity_id": "not-an-int",
    })
    assert resp.status_code == 400


def test_versions_snapshot_unknown_entity_type(client, logged_in_admin):
    resp = client.post("/versions/snapshot", data={
        "entity_type": "spaceship",
        "entity_id": "1",
    })
    assert resp.status_code == 400


def test_versions_snapshot_entity_not_found(client, logged_in_admin):
    resp = client.post("/versions/snapshot", data={
        "entity_type": "member",
        "entity_id": "99999",
    })
    assert resp.status_code == 400


def test_versions_snapshot_success(client, logged_in_admin, seeded_member):
    resp = client.post("/versions/snapshot", data={
        "entity_type": "member",
        "entity_id": str(seeded_member.id),
    })
    assert resp.status_code == 200
    assert b"version" in resp.data.lower()
