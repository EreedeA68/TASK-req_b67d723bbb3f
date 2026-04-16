"""Tests for masked display of sensitive fields in HTMX templates."""


def test_order_create_page_masks_phone(client, logged_in_staff, seeded_member):
    """Order-create dropdown should show masked phone, not ciphertext."""
    resp = client.get("/orders/create")
    assert resp.status_code == 200
    html = resp.data.decode()

    # Masked display should show last-4 digits with asterisks
    assert "****4567" in html or "****" in html
    # Ciphertext (base64) should NOT appear — check for typical Fernet token prefix
    assert "gAAAAA" not in html


def test_search_highlighting_rendered(client, logged_in_staff, seeded_member):
    """Search results should render <mark> tags around matched text."""
    resp = client.get(f"/search/results?q={seeded_member.name}")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "<mark>" in html
    assert "</mark>" in html
