"""Encryption, masking, and sensitive data protection tests."""


def test_encrypt_decrypt_roundtrip(app):
    from app.core.encryption import decrypt, encrypt

    plain = "5551234567"
    ct = encrypt(plain)
    assert ct != plain
    assert decrypt(ct) == plain


def test_encrypt_empty_string(app):
    from app.core.encryption import encrypt

    assert encrypt("") == ""


def test_mask_phone():
    from app.core.encryption import mask_phone

    assert mask_phone("5551234567") == "****4567"
    assert mask_phone("1234") == "****1234"
    assert mask_phone("12") == "****"
    assert mask_phone("") == "****"


def test_mask_balance():
    from app.core.encryption import mask_balance

    assert mask_balance("100.50") == "****"
    assert mask_balance("") == "****"


def test_member_phone_stored_encrypted(app, logged_in_staff, client):
    from app.models.member import Member

    resp = client.post("/api/members", json={
        "name": "Crypto User",
        "phone_number": "5559998888",
        "member_id": "M-CRYPT01",
    })
    assert resp.status_code == 201
    m = Member.query.filter_by(member_id="M-CRYPT01").first()
    assert m is not None
    # Raw column value should NOT be plaintext
    assert m.phone_number != "5559998888"
    assert len(m.phone_number) > 20  # Fernet ciphertext is long


def test_member_balance_stored_encrypted(app, logged_in_staff, client):
    from app.models.member import Member

    resp = client.post("/api/members", json={
        "name": "Balance User",
        "phone_number": "5551110000",
        "member_id": "M-BAL01",
        "stored_value_balance": "150.75",
    })
    assert resp.status_code == 201
    m = Member.query.filter_by(member_id="M-BAL01").first()
    assert m.stored_value_balance != "150.75"


def test_non_admin_sees_masked_phone(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/members/{seeded_member.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["phone_number"].startswith("****")
    assert data["phone_number"] != "5551234567"


def test_non_admin_sees_masked_balance(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/members/{seeded_member.id}")
    data = resp.get_json()
    assert data["stored_value_balance"] == "****"


def test_admin_sees_full_phone(client, logged_in_admin, seeded_member):
    resp = client.get(f"/api/members/{seeded_member.id}")
    data = resp.get_json()
    assert data["phone_number"] == "5551234567"


def test_admin_sees_full_balance(client, logged_in_admin, seeded_member):
    resp = client.get(f"/api/members/{seeded_member.id}")
    data = resp.get_json()
    assert data["stored_value_balance"] == "0"


def test_search_returns_masked_for_staff(client, logged_in_staff, seeded_member):
    resp = client.get(f"/api/members/search?q={seeded_member.member_id}")
    data = resp.get_json()
    assert data["results"][0]["phone_number"].startswith("****")


def test_search_returns_full_for_admin(client, logged_in_admin, seeded_member):
    resp = client.get(f"/api/members/search?q={seeded_member.member_id}")
    data = resp.get_json()
    assert data["results"][0]["phone_number"] == "5551234567"


def test_lookup_by_phone_still_works(client, logged_in_staff, seeded_member):
    """Phone lookup must work even though data is encrypted."""
    resp = client.get("/api/members/search?q=5551234567")
    data = resp.get_json()
    assert data["match"] == "exact"
    assert data["results"][0]["member_id"] == seeded_member.member_id


def test_ui_member_partial_shows_masked_phone(client, logged_in_staff, seeded_member):
    resp = client.get(f"/members/lookup?q={seeded_member.member_id}")
    assert resp.status_code == 200
    assert b"****" in resp.data
    assert b"5551234567" not in resp.data
